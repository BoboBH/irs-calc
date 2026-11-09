# 利率互换(IRS)计算器

银行间利率互换单笔合约计算器:FastAPI + 纯 Python 定价内核 + Vue3/Element Plus 前端,无数据库,行情数据来自本地 CSV。

## 环境要求

- Python 3.12(虚拟环境一律用 `D:/Python312` 创建)
- Node.js(仅前端构建用)

## 安装与启动

```bash
# 1) 后端虚拟环境
D:/Python312/python.exe -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

# 2) 先构建前端(后端启动时才挂载 frontend/dist,顺序反了页面会 404)
cd frontend && npm install && npm run build

# 3) 启动后端
cd ../backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000。

## 开发模式

后端 uvicorn(8000)照常启动,前端另开 `cd frontend && npm run dev`(5173,已配置 /api 代理到 8000)。

## 测试

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest
```

## 对外接入(HTTP API / MCP / Claude Code 技能)

- **HTTP API**:行情/估值/Campisi 归因/平价 4 个端点;单位口径(利率 %、利差 bp)、字段表、错误码与端到端示例见 **[docs/API.md](docs/API.md)**;交互式文档 `/docs`,OpenAPI 契约 `/openapi.json`。
- **MCP**(streamable HTTP,与 API **同端口**):[backend/app/mcp_server.py](backend/app/mcp_server.py) 挂载进 FastAPI,端点 `http://127.0.0.1:8000/mcp`,把 API 1:1 包装成 4 个工具(`load_market` / `value_swap` / `campisi_attribution` / `par_rate`)供 AI agent 调用;工具经 ASGI 进程内直调 API,口径单一实现。注册:`claude mcp add --transport http irs-calc http://127.0.0.1:8000/mcp`。
- **Claude Code 技能**:[.claude/skills/irs-calc/SKILL.md](.claude/skills/irs-calc/SKILL.md)——会话中提及 IRS 估值 / Campisi 归因 / 平价利率 / DV01 / 定盘查询时自动触发,引导按正确口径调 API。

## 估值页默认行为

- 进入估值页**自动加载行情**(无需手动点击)。
- 加载后**固定利率自动同步为当期定盘利率**(如 FR007 当期定盘 1.4%);用户手动修改过固定利率后,不再自动覆盖。
- 合约默认参数:起息日 2026-06-01、期限 3 年、本金交割、贴现口径连续复利。
- **统一口径 = 合约标准 T-1(无双轨)**:定盘取值固定**重置日前一营业日**——CFETS《互换通人民币利率互换产品手册》标准合约要素:FR007 / Shibor 3M 的**首次利率确定日 = 起息日 − 1 个工作日**,利率确定日适用**上一营业日准则**(Shibor O/N 例外取当日);与厂商系统同口径。曲线自动补 **7D 锚点行 = 当期定盘**(普通可编辑行,重新加载行情时按新定盘重建;仅影响首个报价期限之前的曲线段,FR007 定盘本身即 7 天回购利率、期限匹配)。取法仍为 API 参数 `fixing_lag_bd`(0 = 当日,与标准恒差约 860 元/亿、平价 0.032bp,测试钉住)。
- **计算平价**:固定利率旁「计算平价」按钮调 `POST /api/par_rate`,返回**使 NPV=0 的固定利率**(与当前曲线/利差/日期/本金交割口径一致;与方向、名义无关),自动回填输入框,重新「计算估值」应得 NPV≈0。内核用两点线性法(R=0/R=1 各算一次 `value_swap`:固定腿现值对 R 严格线性,斜率 = 年金 N·Στ·df,截距 = 本金现值),利差抬高浮动腿现值故平价随之抬高(测试钉住)。

## 定价与曲线口径

### 定价内核(后端 `backend/app/core/curve.py`)

- **接口层单位口径**:利率一律**百分数**(1.65 = 1.65%)、浮动端利差一律**基点**(`spread_bp`,25 = 25bp,叠加在基准指标之上),前端输入框与 API 同单位直传;内核层一律小数,换算(`/100`、`/10000`)集中在 API 装配层完成;
- 零息收益率曲线**插值方式为参数**(`interp`,经 API `curve_interp` 传入),两种均严格穿过全部报价点、首末期限之外**两端平推**:
  - **`linear`(默认)——零利率线性插值**;贴现与浮动端未来重置利率预测(远期)均按此口径;
  - **`hermite`——单调三次 Hermite(Fritsch–Carlson)**:节点切线连续、有弧度,局部极值点切线取 0 保证单调无过冲,两端切线取 0 与平推衔接;即中债官方收益率曲线同款插值;
- 贴现因子 `df = exp(-y·τ)`(连续复利,τ = 天数 / 365);浮动端重置利率取区间远期 `(df(d1)/df(d2) − 1)/τ`,远期随插值口径自动变化;
- 平推区(早于首个报价期限)两种插值取值相同,远期亦一致;
- 与厂商的逐分位对齐在「`linear` + 连续复利 + **T-1 定盘**(默认)+ 7D 锚点」下成立(后端测试钉住),页面默认口径即厂商口径——平价利率亦逐位一致(2026-11-06 FR007 3Y:厂商 **1.3546** = 本内核 T-1 口径 1.354603;当日口径为 1.354284);切 `hermite` 后 NPV/DV01 随插值变化(约 +3,289 元),属口径切换而非误差;DV01 移动曲线与归因静态曲线继承同一插值口径。

### 前端曲线显示(`frontend/src/views/Valuation.vue`)

- **按基准重置周期细采样**:FR007 每周、Shibor 3M 每季取一个点(10Y 约 500+ 点),避免 11 个报价点直连的折线感;
- **插值方式 = 左侧参数区「曲线插值」单选**(定价参数,随请求发送,与「贴现口径」同区;切换后需重新「计算估值」生效,而**图立即重绘**);
  - **线性(默认)**——零利率线性,与定价内核同法;
  - **Hermite**——单调三次,前端显示层与内核 `_hermite_tangents` 同法,两种模式下均保持 **图 = 定价所用曲线**;
- Y 轴 nice 刻度(1/2/5×10^k,约 5~7 格),保证曲线最低点下方有刻度;横轴刻度取报价期限点,短端过密时自动跳过(首末刻度必显)。

## 数据依赖

运行与测试需要 `data/` 目录下的 CSV(**已入库**便于复现与验证;行情为快照数据,刷新行情时直接覆盖文件):

- `rate_value.csv`:估值曲线(按基准/日期的期限点零息利率)
- `rate_info.csv`:期限与定盘信息

`FR007ON行情.csv`、`SHIBOR3M定盘行情.csv` 为原始行情留档,当前 loader 不读取。

定价/归因方法论参考:`docs/九鞅科技利率互换Campisi归因方法白皮书 V1 20261106.pdf`(已入库)。
