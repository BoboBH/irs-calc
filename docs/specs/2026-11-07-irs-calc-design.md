# 利率互换计算器(IRS Calc)详细设计

日期:2026-11-07
状态:待审批
方法论依据:《九鞅科技利率互换Campisi归因方法白皮书 V1 20261106.pdf》(项目根目录)

## 1. 目标与范围

### 1.1 目标

Web 界面输入利率互换合约信息与市场数据,后端完成:

1. **定价**:NPV、固定腿 PV、浮动腿 PV
2. **现金流**:固定腿 / 浮动腿未来现金流明细表
3. **风险**:平行 DV01、关键期限 DV01(KRDV01,三角形权重)
4. **Campisi 日频归因**:ΔNPV 分解为 Θ(时间)、Carry(票息)、Roll(骑乘)、Curve(曲线)、Spread(=0)、ε(残差),满足勾稽恒等式

### 1.2 范围

- **基准利率**:FR007(优先,测试基准)、SHIBOR 3M(同一框架支持)
- **形态**:单笔交易、无数据库、无用户系统
- **不做**:曲线构建(bootstrap)、交易管理、组合汇总、多期(>1 区间)归因累加、坏点自动清洗

## 2. 总体架构

```
irs-calc/
├── backend/                      # Python 3.12 + FastAPI
│   ├── app/
│   │   ├── main.py               # FastAPI 入口;生产模式托管前端构建产物
│   │   ├── api/
│   │   │   ├── market.py         # GET /api/market 按日加载曲线+定盘(供前端预填)
│   │   │   ├── valuation.py      # POST /api/value 单日估值
│   │   │   └── attribution.py    # POST /api/attribution 区间归因
│   │   ├── dataio/
│   │   │   └── loader.py         # 读 data/*.csv:曲线行情、定盘序列、品种表
│   │   └── core/                 # 计算内核:纯函数、无框架依赖、全部可单测
│   │       ├── calendar.py       # 交易日历(见 §4.6)、营业日调整
│   │       ├── conventions.py    # FR007 / SHIBOR3M 惯例配置(表驱动)
│   │       ├── schedule.py       # 付息排期 + FR007 周重置子区间
│   │       ├── curve.py          # 零息曲线:DF、插值、平行/关键期限扰动
│   │       ├── pricing.py        # 双腿现金流与 PV、NPV
│   │       ├── risk.py           # 平行 DV01、KRDV01
│   │       └── attribution.py    # Campisi 分解(白皮书口径)
│   └── tests/                    # pytest(手算基准 + 性质断言)
├── frontend/                     # Vue 3 + Element Plus + Vite + axios
│   └── src/
│       ├── views/Valuation.vue   # 单页:表单 + 市场数据 + 结果区
│       └── api/client.js
├── data/                         # 既有行情数据(不改动格式)
│   ├── rate_info.csv             # 品种表(sec_id, name, sec_code, BMK_IDX, tenor)
│   └── rate_value.csv            # 行情(sec_id, date, value),含互换报价与定盘
└── docs/specs/
```

数据流:前端表单 → `POST /api/value|/api/attribution` → 后端:参数校验 → 读行情(loader)→ 查惯例 → 生成排期 → 构建曲线 → 现金流与 PV → 风险/归因 → 返回 JSON → 前端渲染。

## 3. 数据文件与加载(dataio/loader.py)

- 行情文件 `data/rate_value.csv`:Tab 分隔,UTF-8,列 `sec_id|date|value`。sec_id 含千分位逗号,按字符串处理,不转 int
- 品种表 `data/rate_info.csv`:按 BMK_IDX(CNY-FR007 / CNY-SHIBOR-3M)区分基准
  - FR007 互换 11 个期限点:1M,3M,6M,9M,1Y,2Y,3Y,4Y,5Y,7Y,10Y
  - SHIBOR3M 互换 9 个期限点:6M~10Y
  - 定盘:51,557 = FR007 定盘;51,558 = SHIBOR 3M 定盘
- 提供函数:`load_curve(date, benchmark) -> {tenor: rate}`、`load_fixings(benchmark) -> {date: rate}`、`load_instruments()`
- **长端坏点一期不清洗**(用户决策);曲线在界面可编辑,可手动改值后再计算
- 行情缺失某日期 → API 返回明确错误信息

## 4. 金融口径与公式(核心)

### 4.1 符号

与白皮书一致:ω = +1 收固定 / −1 付固定;N 名义本金;K 固定利率;s 浮动腿利差(默认 0);C_t 零息曲线;L_d = d 日定盘利率。

### 4.2 曲线(curve.py)

- **输入**:估值日 + 关键期限零息利率表(单位 %,内部转小数)
- **贴现因子**:`DF(T) = 1 / (1 + y·τ)`,τ = 实际天数/365(ACT/365),T 以估值日为 0 点;
  另支持 `discount_basis="cont"`(连续复利 `DF = exp(−y·τ)`,与外部厂商系统对账用,默认 simple,平移曲线继承口径)
- **插值**:关键期限之间零息利率线性插值;两端之外零利率平推外推
- **扰动**(risk.py 用):
  - 平行:全部期限点 y + 1bp
  - 关键期限 k:点 k 上 y + 1bp,相邻关键期限间按线性(三角形)权重分摊,保证 **Σ KRDV01_k = 平行 DV01**
- 期限点日期 = 估值日 + 期限(1M/3M/…按日历月;1Y 按年;7D 等日历日标签按天数,厂商曲线锚点用)

### 4.3 排期(schedule.py)

**固定腿**(FR007 与 SHIBOR3M):
- 付息频率:季度(默认,可选项:年度),自起息日起按日历月推;修正顺延(Modified Following,中国日历)调整
- 计息:按**调整后**实际天数计 ACT/365(FR007)/ ACT/360(SHIBOR3M)

**浮动腿 FR007**:
- 每个季度付息期内部,自该期起息日(调整后)**每 7 个日历日**拆一个重置子区间,末段截断至季度末(子区间边界不调整)
- 每个子区间利率:重置日 ≤ 估值日 → 当日 FR007 定盘(重置日非交易日则取之前最近定盘);重置日 > 估值日 → 曲线隐含远期。
  另支持 `fixing_lag_bd`(定盘观察日前移 N 个营业日,厂商 T-1 口径:取值用观察日 ≤ 估值日判断、显示 reset_date = 观察日,默认 0)
- 季度现金流:`CF = N · Σₖ(rₖ·τₖ)`,τₖ = 子区间实际天数/365(分段加总,银行间通行口径)
- 支付日 = 季度末付息日(修正顺延),支付额在支付日计入
- `principal_exchange`(本金交割,厂商口径):到期时两腿各并入名义本金 N(NPV/DV01 中性,改变两腿 PV 与末行金额;仅当末行支付日 > 估值日时并入,默认关)

**浮动腿 SHIBOR3M**:按季重置按季付;重置日 ≤ 估值日用 3M Shibor 定盘,否则用隐含 3M 远期;ACT/360。

**远期公式**(两基准同):`F(t1→t2) = (DF(t1)/DF(t2) − 1) / τ(t1,t2)`

### 4.4 定价(pricing.py)

- 固定腿:`PV_fix = Σᵢ N·K·τᵢ·DF(支付日ᵢ)`
- 浮动腿:`PV_flt = Σⱼ CFⱼ·DF(支付日ⱼ)`
- `NPV = ω·(PV_fix − PV_flt)`(含头寸方向,单位:元)

### 4.5 风险(risk.py)

- 平行 DV01 = `NPV(曲线全体+1bp) − NPV(基准曲线)`(含 ω,元/bp)
- KRDV01_k = 静态扰动的 NPV 变动(同上),逐关键期限输出
- 关键期限集合 = 该基准全部期限点中,**≤ t1 时点剩余期限向上取整所需**的点(白皮书"仅保留覆盖剩余期限所需的点")

### 4.6 交易日历(calendar.py)

- **交易日历来源:FR007 定盘日期序列**(51,557 有定盘的日期 = 银行间交易日,457 天,2025-01-02 ~ 2026-11-06),loader 生成 `trading_days.json`
- 范围外日期(2024 年尾部、2027+):回退"周六周日非交易日、无节假日"规则,并在日历响应中标注 `approximate: true`
- 营业日调整:修正顺延(下一交易日,若跨月则往前)

### 4.7 Campisi 归因(attribution.py,白皮书公式逐条落地)

输入:t0、t1(相邻估值日,t0<t1)、两日曲线 C_t0 / C_t1(自动从行情加载,界面可改)、合约要素。

| 分项 | 公式 | 实现要点 |
|---|---|---|
| 全价损益 | `ΔNPV = NPV(t1;C_t1) + CF(t0,t1] − NPV(t0;C_t0)` | CF = 区间内实际支付日落在 (t0,t1] 的净现金流(含 ω) |
| 静态曲线 | `C̃_t1`:各期限零息利率 = C_t0 的值,估值日推进至 t1 | 区间内新重置的浮动利率按 C̃ 隐含远期(白皮书口径);t0 前已定盘的仍用真实定盘 |
| 时间效应 | `Θ = NPV(t1;C̃_t1) + CF − NPV(t0;C_t0)` | |
| 票息效应 | `Carry = ω·N·[K·τfix(t0,t1) − (L0+s)·τflt(t0,t1)]` | L0 = t0 所在重置子区间重置日的已定盘利率(自动从定盘序列取,界面可改);τ 按各自计息惯例,τflt(t0,t1) 为 (t0,t1] 内各子区间实际天数/365 之和 |
| 骑乘效应 | `Roll = Θ − Carry` | 轧差法,保证 Θ = Carry + Roll 精确成立 |
| 曲线效应 | `Curve = Σₖ KRDV01ₖ·Δyₖ` | KRDV01ₖ 在 (t1; C̃_t1) 处计算(白皮书展开点);Δyₖ = y_t1(Tₖ) − y_t0(Tₖ),constant maturity |
| 利差效应 | `Spread = 0` | 单曲线框架 |
| 残差 | `ε = ΔNPV − Θ − Curve` | 含凸性、交叉项、定盘与远期之差 |

**勾稽校验(硬性)**:`Carry + Roll + Curve + Spread + ε = ΔNPV`,后端以数值恒等式断言并在响应中返回校验状态。

## 5. API 设计

统一前缀 `/api`,JSON;错误统一 `{code, message}`(HTTP 400 参数错 / 422 业务错 / 500 内部错)。

### 5.1 GET /api/market?date=YYYY-MM-DD&benchmark=FR007

按日预填:`{curve: [{tenor, rate, sec_id}], fixing: {date, rate}, calendar_approximate: bool}`。定盘取 ≤ date 最近一条;曲线缺该日期报 404 样错误。

### 5.2 POST /api/value(单日估值)

```jsonc
请求:
{
  "benchmark": "FR007",              // FR007 | SHIBOR3M
  "direction": "receiver",           // receiver=收固定 | payer=付固定
  "notional": 100000000,
  "fixed_rate": 1.65,                // %
  "spread": 0,                       // %,默认 0
  "effective_date": "2026-05-28",
  "maturity_date": "2029-05-28",
  "fixed_freq": "quarterly",         // quarterly | annual
  "valuation_date": "2026-11-06",
  "curve": [ {"tenor": "1M", "rate": 1.3838}, ... ],   // 可选;缺省自动从行情加载
  "fixing_overrides": { "2026-11-05": 1.37 }           // 可选;覆盖个别定盘
}
响应:
{
  "npv": -1234567.89, "pv_fixed": ..., "pv_floating": ...,
  "dv01_parallel": ...,
  "krdv01": [ {"tenor": "1M", "dv01": ...}, ... ],
  "cashflows": {
    "fixed":  [ {"pay_date": "...", "accrual": {"start": "...", "end": "...", "days": 91, "tau": 0.2493},
                 "rate": 1.65, "amount": ..., "df": ..., "pv": ...} ],
    "floating": [ {"pay_date": "...", "period": {...},
                   "sub_periods": [ {"reset_date": "...", "rate": ..., "source": "fixing|forward", "days": 7, "tau": ...} ],
                   "amount": ..., "df": ..., "pv": ...} ]
  },
  "warnings": [ ... ]                // 如:定盘缺失已按输入值处理、日历为近似模式
}
```

### 5.3 POST /api/attribution(区间归因)

在 5.2 请求基础上增加 `"start_date": "2026-11-05"`(t0,曲线自动加载,也可显式给 `start_curve`);t1 = valuation_date。响应:

```jsonc
{
  "pnl": { "delta_npv": ..., "cf": ... },            // 全价损益与区间现金流
  "components": {
    "theta": ..., "carry": ..., "roll": ..., "curve": ..., "spread": 0, "residual": ...
  },
  "check": { "identity_ok": true, "diff": 1e-9 },    // 勾稽校验
  "curve_effect_detail": [ {"tenor": "1M", "dy_bp": ..., "krdv01": ..., "contribution": ...} ],
  "valuation_t1": { ... }                            // 同 /api/value 的 t1 估值结果(复用)
}
```

## 6. 界面设计(Vue 3 + Element Plus,单页)

```
┌────────────────────────────────────────────────────────┐
│ ① 合约信息(表单卡)                                     │
│   基准FR007▾  方向收/付固定▾  名义本金  固定利率%  利差% │
│   起息日  到期日  固定腿频率季▾                          │
│ ② 市场数据(卡)                                         │
│   估值日t1 [2026-11-06] 归因起始日t0 [2026-11-05](选填) │
│   [加载行情] → 曲线表格(期限|利率,可编辑) + 当日定盘显示 │
│   [计算估值]  [计算归因](t0 已填时可用)                  │
│ ③ 结果区(Tabs)                                         │
│   Tab1 估值摘要:NPV / PV固定 / PV浮动 / 平行DV01 大数卡片│
│   Tab2 关键期限DV01:表格(期限|KRDV01)+ 合计=平行DV01 校验│
│   Tab3 现金流:固定腿 / 浮动腿两张表(浮动腿含重置子区间)  │
│   Tab4 Campisi归因:ΔNPV 分解瀑布卡(Θ/Carry/Roll/Curve/ε)│
│         + Curve 明细表(Δyₖ × KRDV01ₖ)+ 勾稽校验状态     │
└────────────────────────────────────────────────────────┘
```

- 金额千分位,利率/DV01 保留 4 位;PV、归因分项均为元(含方向),负值红色
- 警告(定盘缺失、近似日历、空值期限点)用 ElAlert 展示在结果区顶部

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| 参数非法(日期倒序、本金≤0、到期≤估值日等) | 400 + 字段级中文错误信息 |
| 行情无该日期曲线 / 定盘缺失 | 曲线缺失→422 报错;定盘缺失→警告 + 使用界面输入值 |
| t0 无曲线(归因) | 422,提示该日无行情 |
| 内部计算异常 | 500 + message,后端记录日志 |

Python 日志按用户全局规范:滚动文件(按天 + 50MB),保留 7 天,全局单 handler。

## 8. 测试策略(pytest,FR007 优先)

1. **手算基准**:构造小案例(如 N=1亿、1 年期、季付、平缓曲线),每个 DF/CF/PV 手工可验,断言到 0.01 元
2. **性质断言**(白皮书保证的恒等式):
   - Σ KRDV01_k = 平行 DV01(三角形权重性质)
   - Carry + Roll = Θ;Θ + Curve + ε = ΔNPV(勾稽)
   - 平价互换(按曲线平价率成交)NPV ≈ 0
   - DF 单调递减(正利率下);远期利率 > 0
3. **排期测试**:季度数正确;周子区间天数之和 = 季度实际天数;调整后支付日均为交易日
4. **归因回归**:用真实数据(2026-11-05→11-06,FR007)跑通并固定快照值,防回归
5. SHIBOR3M:同框架冒烟测试(计息 ACT/360、定盘取数正确)

## 9. 实施顺序

1. **内核 + 测试**(core 六模块 + pytest,先 FR007)
2. **API + 数据加载**(dataio + 三个接口,FastAPI 启动)
3. **前端**(Vite 脚手架、表单、结果区、联调)
4. 端到端验收:界面输入合约 → 估值/归因 → 勾稽通过

## 10. 已知简化与风险

| 项 | 说明 |
|---|---|
| 互换报价当零息利率用 | 一期不做 bootstrap;报价≈即期零利率是近似,归因/估值同口径下自洽 |
| 长端坏点不清洗 | 用户决策;界面可手动改曲线;二期再考虑自动清洗 |
| FR007 周子区间边界不调整 | 与常见厂商口径一致;定盘按"重置日当日或之前最近"取 |
| 日历范围外近似 | 2027+ 无真实交易日数据,回退周末规则,已标注 approximate |
| 估值口径为 ex-coupon | NPV 只含未来现金流;区间内已付现金流走 CF 项,与白皮书 ΔNPV 口径一致 |
