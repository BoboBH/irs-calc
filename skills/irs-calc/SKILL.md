---
name: irs-calc
description: 调用本地利率互换(IRS)计算器服务:估值(NPV/DV01/现金流)、Campisi 归因(theta/carry/roll/curve/spread)、平价利率、FR007/Shibor 3M 行情曲线与定盘查询。当用户要求 IRS 估值、Campisi 归因分析、平价利率、DV01 或查询行情曲线/定盘时使用。需本机服务已启动(http://127.0.0.1:8000)。
---

# IRS 计算器 API 调用指南

银行间 IRS(FR007/Shibor 3M)单笔合约计算器。FastAPI 后端,本文教你用 curl 正确调用。
若本项目已注册 MCP(streamable HTTP,端点 `http://127.0.0.1:8000/mcp`;`claude mcp list`
可见 `irs-calc`),优先直接用 MCP 工具(load_market / value_swap / campisi_attribution /
par_rate),语义与下文 API 相同。

## 0. 健康检查与行情加载

```bash
# 服务是否在跑(非 200 → 先启动:cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000)
curl -s "http://127.0.0.1:8000/api/market?benchmark=FR007&date=2026-11-06"
# → {benchmark, valuation_date, curve:[{tenor,rate}...11点], fixing:{date,rate}, calendar_approximate}
```

## 1. 单位与缺省口径(错了数字就不对)

| 参数 | 单位/取值 | 缺省 |
|---|---|---|
| `fixed_rate`、曲线点 `rate`、`fixing_overrides` 值 | **百分数**(1.65 = 1.65%) | — 必填 |
| `spread_bp` | **基点**(25 = 25bp) | 0 |
| 日期(`effective_date` 等) | ISO 串 "2026-11-06" | — 必填 |
| `curve` | `[{tenor,rate}]`;**`[]` = 按估值日自动加载行情曲线** | `[]` |
| `fixing_lag_bd` | 1 = 合约标准 T-1 定盘(CFETS);0 = 当日(旧取法) | 1 |
| `discount_basis` | `simple` 单利 / `cont` 连续复利 | `simple`(**页面是 cont**) |
| `principal_exchange` | 到期两腿互换本金 | false(**页面是 true**) |
| `curve_interp` | `linear`(厂商对齐)/ `hermite`(中债同款) | `linear` |

**对账前端页面/厂商系统** → 显式传 `discount_basis:"cont"`、`principal_exchange:true`
(曲线可用页面同款:7D 锚点行 = 当期定盘 + 行情 11 点)。

## 2. 估值 POST /api/value

```bash
curl -s -X POST http://127.0.0.1:8000/api/value -H "Content-Type: application/json" -d '{
  "benchmark":"FR007", "direction":"receiver", "notional":100000000,
  "fixed_rate":1.4, "spread_bp":0,
  "effective_date":"2026-06-01", "maturity_date":"2029-06-01", "valuation_date":"2026-11-06",
  "discount_basis":"cont", "principal_exchange":true, "fixing_lag_bd":1, "curve":[]
}'
# → {npv, pv_fixed, pv_floating, dv01_parallel, krdv01:[{tenor,dv01}],
#    cashflows:{fixed:[...],floating:[...]}, warnings:[...]}   金额均元
```

`direction`:receiver=收固定付浮动;`fixed_freq_months` 固定腿付息周期(缺省 3;浮动端随基准,FR007 周、Shibor3M 季)。

## 3. Campisi 归因 POST /api/attribution(核心)

```bash
curl -s -X POST http://127.0.0.1:8000/api/attribution -H "Content-Type: application/json" -d '{
  "benchmark":"FR007", "direction":"receiver", "notional":100000000,
  "fixed_rate":1.4, "spread_bp":0,
  "effective_date":"2026-06-01", "maturity_date":"2029-06-01", "valuation_date":"2026-11-06",
  "discount_basis":"cont", "principal_exchange":true, "fixing_lag_bd":1, "curve":[]
}'
```

返回:`{delta_npv, cf(窗口内已付现金流), components:{theta,carry,roll,curve,spread,residual},
detail:[逐关键期限], identity:{ok,diff}, valuation_t1:{窗口末全量估值}, warnings}`。

- 恒等式:ΔNPV = theta+carry+roll+curve+spread+residual(**构造上恒成立**);
- 因子:theta=静态曲线推进的时间效应,carry=票息效应(固定利息−浮动计提),roll=theta−carry(骑乘),
  curve=关键期限 KRDV01×曲线变动,spread 恒 0(单曲线);
- **curve 两种模式**:`curve:[]` → 自动加载 t0/T 两日真实行情曲线(curve 分量为真实曲线效应);
  显式 curve → 两日同形(curve≡0,纯时间分解,页面即此模式);
- `identity.ok=false` = 残差门(5%·max(|ΔNPV|,|Curve|,1))拒绝:一阶分解不干净(常见于
  两日曲线大幅移动+单利贴现),因子仍成立但解读需谨慎;
- `start_date` 留空 = 自动取行情中估值日的上一交易日;估值日为非交易日 → 全零归因+warning(正常语义);
- 方法论见仓库 `docs/九鞅科技利率互换Campisi归因方法白皮书 V1 20261106.pdf`。

## 4. 平价利率 POST /api/par_rate

请求同估值(方向/名义/固定利率不参与);返回 `{par_rate(%), annuity, pv_floating}`。
把 `par_rate` 代回估值的 `fixed_rate` 应得 NPV≈0。真实行情参考(2026-11-06 FR007 3Y,
cont+T-1+7D 锚):**1.3546%**(与厂商逐位一致)。

## 5. 错误处理

| HTTP | 含义 | 处理 |
|---|---|---|
| 400 | 参数非法(detail 含中文字段名,如"起息日必须早于到期日") | 改参数重试 |
| 404 | 该日期无行情 | 换日期(GET /api/market 试相邻交易日) |
| 422 | pydantic 校验失败(detail 列出字段) | 按 loc/msg 修 JSON |
| 503 | 行情文件不可读 | 服务端问题,报告用户 |

定盘缺失(估值日早于 2025-01-02 且无 overrides)→ 422 detail 含"定盘"。

## 6. 机器可读契约

`http://127.0.0.1:8000/openapi.json`(完整 schema,可代码生成);交互式文档 `/docs`。
完整人工文档见仓库 `docs/API.md`。
