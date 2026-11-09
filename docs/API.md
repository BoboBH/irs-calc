# IRS 计算器服务调用文档

本服务提供银行间利率互换(FR007 / Shibor 3M)单笔合约的估值、Campisi 归因、平价利率与行情查询。三种接入方式:

| 方式 | 适用 | 入口 |
|---|---|---|
| **HTTP API**(本文) | 人工程序调用、脚本、任何语言 | `http://127.0.0.1:8000` |
| **MCP** | AI agent(Claude Code / Claude Desktop 等) | `http://127.0.0.1:8000/mcp`(streamable HTTP,与 API 同端口) |
| **Claude Code 技能** | 本仓库内的 Claude Code 会话 | `.claude/skills/irs-calc/SKILL.md` |

交互式文档(浏览器直接打开):**`http://127.0.0.1:8000/docs`**(Swagger UI,可在线试调);机器可读契约:`http://127.0.0.1:8000/openapi.json`(可直接代码生成客户端)。

## 启动服务

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

前端(可选,页面用):`cd frontend && npm run dev`(5173,已代理 /api)。

## 单位与缺省口径

**利率一律百分数**(1.65 = 1.65%),**利差一律基点**(`spread_bp`,25 = 25bp),**日期一律 ISO 串**("2026-11-06"),**金额一律元**。

| 字段 | 说明 | API 缺省 | 前端页面口径 |
|---|---|---|---|
| `benchmark` | `FR007` / `SHIBOR3M` | — 必填 | FR007 |
| `direction` | `receiver` 收固定付浮动 / `payer` | — 必填 | receiver |
| `notional` | 名义本金(元) | — 必填(par_rate 可省,不参与) | 1 亿 |
| `fixed_rate` | 固定利率 % | — 必填(par_rate 可省) | 随当期定盘 |
| `spread_bp` | 浮动端利差,基点 | 0 | 0 |
| `effective_date` / `maturity_date` / `valuation_date` | 起息 / 到期 / 估值日;估值日须 ≤ 到期 | — 必填 | — |
| `fixed_freq_months` | 固定腿付息周期(月,1–12) | 3 | 3 |
| `curve` | 零息曲线 `[{tenor,rate}]`;**`[]` = 按估值日自动加载行情曲线** | `[]` | 7D 锚(当期定盘)+ 行情 11 点 |
| `fixing_overrides` | 定盘覆盖 `{ISO日期: rate%}`,一般留空(自动加载) | `{}` | `{}` |
| `discount_basis` | `simple` 单利(白皮书)/ `cont` 连续复利 | `simple` | **`cont`** |
| `curve_interp` | `linear` 零利率线性(厂商对齐)/ `hermite` 单调三次 | `linear` | linear |
| `fixing_lag_bd` | 定盘观察日前推营业日数;**1 = 合约标准 T-1**(CFETS 标准合约要素:首次利率确定日 = 起息日 − 1 个工作日);0 = 当日(旧取法) | 1 | 1 |
| `principal_exchange` | 到期两腿互换本金 | false | **true** |

> **与页面对账**:显式传 `discount_basis:"cont"` + `principal_exchange:true`,曲线用 7D 锚点行(=当期定盘)+ 行情 11 点。

---

## 1. GET /api/market — 行情曲线与定盘

```bash
curl -s "http://127.0.0.1:8000/api/market?benchmark=FR007&date=2026-11-06"
```

```json
{"benchmark":"FR007", "valuation_date":"2026-11-06",
 "curve":[{"tenor":"1M","rate":1.3838}, "...共 11 点 1M→10Y"],
 "fixing":{"date":"2026-11-06","rate":1.4}, "calendar_approximate":false}
```

`fixing` 为 `null` 表示该日早于定盘序列起点(2025-01-02);`calendar_approximate=true` 表示处于 FR007 定盘序列之前的换算期,日历为近似。

## 2. POST /api/value — 估值

```bash
curl -s -X POST http://127.0.0.1:8000/api/value -H "Content-Type: application/json" -d '{
  "benchmark":"FR007","direction":"receiver","notional":100000000,
  "fixed_rate":1.4,"spread_bp":0,
  "effective_date":"2026-06-01","maturity_date":"2029-06-01","valuation_date":"2026-11-06",
  "discount_basis":"cont","principal_exchange":true,"fixing_lag_bd":1,"curve":[]
}'
```

返回:

| 字段 | 说明 |
|---|---|
| `npv` | 合约现值(元;receiver 视角) |
| `pv_fixed` / `pv_floating` | 固定腿 / 浮动腿现值(含本金交割金额,若开) |
| `dv01_parallel` | 平行 DV01:曲线整体 +1bp 的 NPV 变化(元/bp) |
| `krdv01` | 关键期限 DV01 `[{tenor, dv01}]`(7D–10Y,合计 ≈ 平行 DV01) |
| `cashflows` | `{fixed:[...], floating:[...]}` 逐期现金流(支付日/计息区间/天数/利率 %/金额;floating 含 sub_periods 与来源 fixing/forward) |
| `warnings` | 非致命告警(如定盘陈旧) |

估值日为非交易日无此限制(仍可估值);估值日 > 到期日 → 400。

## 3. POST /api/attribution — Campisi 归因

请求同估值 + 可选 `start_date`(窗口起点 t0;**留空 = 自动取行情中估值日的上一交易日**)。

```bash
curl -s -X POST http://127.0.0.1:8000/api/attribution -H "Content-Type: application/json" -d '{
  "benchmark":"FR007","direction":"receiver","notional":100000000,
  "fixed_rate":1.4,"spread_bp":0,
  "effective_date":"2026-06-01","maturity_date":"2029-06-01","valuation_date":"2026-11-06",
  "discount_basis":"cont","principal_exchange":true,"fixing_lag_bd":1,"curve":[]
}'
```

返回:`{delta_npv, cf, components, detail, identity, valuation_t1, warnings}`。

**Campisi 因子分解**(窗口 `(start_date, valuation_date]`,方法论见 `docs/九鞅科技利率互换Campisi归因方法白皮书 V1 20261106.pdf`):

| 因子 | 含义 |
|---|---|
| `theta` | 静态曲线推进的总时间效应(npv_static + cf − npv_t0) |
| `carry` | 票息效应:固定利息 − 浮动计提(L0+spread × τ) |
| `roll` | 骑乘效应:theta − carry |
| `curve` | 曲线效应:关键期限 KRDV01 × 曲线变动之和(`detail` 为逐关键期限明细) |
| `spread` | 利差效应;单曲线口径恒 0 |
| `residual` | 残差:ΔNPV − 各因子之和 |

- **恒等式构造上恒成立**:ΔNPV = theta+carry+roll+curve+spread+residual;`cf` 为窗口内已支付现金流;
- **curve 两种模式**:显式 `curve` → 两日同形,`curve` 分量恒 0(纯时间分解,页面模式);`curve:[]` → 自动加载 t0/T 两日真实行情曲线,`curve` 分量为真实曲线变动效应;
- **`identity.ok`**:恒等式重加总 + ΣKRDV01 机制校验 + 残差门(5%·max(|ΔNPV|,|Curve|,1))三者综合。`false` = 残差门拒绝(两日曲线大幅移动 + 单利贴现时一阶展开不干净),因子数值仍成立但解读需谨慎;`identity.diff` 仅为浮点噪声口径;
- 估值日为**非交易日** → 200 全零归因 + warning(正常语义,非错误);`start_date` ≥ `valuation_date` → 422。

示例(2026-11-05→11-06 窗口,cont+PE+显式曲线):ΔNPV = −79.81 = theta(−79.81)+curve(0)+…,identity ok=true;同窗口改 `curve:[]`(两日真实行情):curve 分量 6093.65、residual 6825.44、identity ok=false(门如实拒绝)。

## 4. POST /api/par_rate — 平价利率

使 NPV=0 的固定利率(市场公允固定利率)。与估值同口径;**方向、名义、固定利率不参与**(线性消去,可省)。利差抬高平价,本金交割不影响。

```bash
curl -s -X POST http://127.0.0.1:8000/api/par_rate -H "Content-Type: application/json" -d '{
  "benchmark":"FR007","effective_date":"2026-06-01","maturity_date":"2029-06-01",
  "valuation_date":"2026-11-06","discount_basis":"cont","fixing_lag_bd":1,
  "curve":[{"tenor":"7D","rate":1.4},{"tenor":"1M","rate":1.3838},"...7D 锚+11 点"]
}'
# → {"par_rate":1.354603,"annuity":270278831.17,"pv_floating":...}
```

`par_rate`(%) 代回估值的 `fixed_rate` 应得 NPV≈0(回填 6 位小数时残差 ~1 元量级)。参考:2026-11-06 FR007 3Y(cont+T-1+7D 锚)**1.3546%**,与厂商系统逐位一致。

## 5. 错误码

| HTTP | 场景 | detail 特征 |
|---|---|---|
| 400 | 参数非法(起息 ≥ 到期、估值 > 到期、非法 tenor 等) | 中文说明,含字段名 |
| 404 | 该基准该日期无行情 | "无行情…" |
| 422 | pydantic 校验失败 / 定盘缺失 | `detail` 为字段列表(loc/msg)或含"定盘" |
| 503 | 行情 CSV 不可读 | "数据文件…" |

## 6. MCP 接入(AI agent)

**streamable HTTP、与 API 同端口**:MCP 端点就是 `http://127.0.0.1:8000/mcp`,由同一 uvicorn 进程挂载([backend/app/mcp_server.py](../backend/app/mcp_server.py));工具经 ASGI 在进程内直调上列 HTTP 接口——schema 校验/缺省值/错误映射与外部调用逐字一致,**无独立进程、无需额外配置**。启动服务即同时提供 API 与 MCP。

| 工具 | 对应 API | 说明 |
|---|---|---|
| `load_market(benchmark, date)` | GET /api/market | 行情曲线 + 定盘 |
| `value_swap(benchmark, effective_date, maturity_date, valuation_date, …)` | POST /api/value | NPV/DV01/现金流 |
| `campisi_attribution(…, start_date=None)` | POST /api/attribution | Campisi 因子 |
| `par_rate(benchmark, effective_date, maturity_date, valuation_date, …)` | POST /api/par_rate | 平价利率 |

工具参数与 API 字段**同名同义**(利率百分数、利差基点、curve 空数组自动加载),docstring 内含全部口径说明。

**Claude Code 注册**:

```bash
claude mcp add --transport http irs-calc http://127.0.0.1:8000/mcp
# 其他 MCP 客户端同理:transport=streamable http,url 指向 /mcp
```

**Claude Desktop**:设置 → Connectors → 添加自定义连接器,URL 填 `http://127.0.0.1:8000/mcp`。

手动冒烟(应 200 并返回含 `serverInfo` 的握手结果):

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

## 7. Claude Code 技能

仓库自带项目技能 `.claude/skills/irs-calc/SKILL.md`:在 Claude Code 中提到"IRS 估值 / Campisi 归因 / 平价利率 / DV01 / FR007 定盘"即自动触发,内含健康检查、口径表、curl 模板与错误处理(与本文一致)。已注册 MCP 时优先走 MCP 工具。

## 8. 最小客户端示例

Python(requests):

```python
import requests
BASE = "http://127.0.0.1:8000"
req = {"benchmark":"FR007","direction":"receiver","notional":100_000_000,
       "fixed_rate":1.4,"spread_bp":0,
       "effective_date":"2026-06-01","maturity_date":"2029-06-01",
       "valuation_date":"2026-11-06","discount_basis":"cont",
       "principal_exchange":True,"fixing_lag_bd":1,"curve":[]}
v = requests.post(f"{BASE}/api/value", json=req, timeout=60).json()
a = requests.post(f"{BASE}/api/attribution", json=req, timeout=60).json()
print(v["npv"], a["components"])   # 122494.77 {'theta': -79.81, ...}
```

JavaScript(fetch):

```js
const r = await fetch("http://127.0.0.1:8000/api/par_rate", {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({benchmark:"FR007", effective_date:"2026-06-01",
    maturity_date:"2029-06-01", valuation_date:"2026-11-06",
    discount_basis:"cont", fixing_lag_bd:1, curve:[]}),
}).then(r => r.json());
console.log(r.par_rate);   // 1.3546(同口径)
```
