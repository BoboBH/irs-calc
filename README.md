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

## 估值页默认行为

- 进入估值页**自动加载行情**(无需手动点击)。
- 加载后**固定利率自动同步为当期定盘利率**(如 FR007 当期定盘 1.4%);用户手动修改过固定利率后,不再自动覆盖。
- 合约默认参数:起息日 2026-06-01、期限 3 年、本金交割、贴现口径连续复利。

## 定价与曲线口径

### 定价内核(后端 `backend/app/core/curve.py`)

- 零息收益率曲线:报价期限点之间**零利率线性插值**,首末期限之外**两端平推**;
- 贴现因子 `df = exp(-y·τ)`(连续复利,τ = 天数 / 365);
- **NPV/DV01 以此口径与厂商逐分位对齐**,改插值方法会破坏对齐,须重新校准。

### 前端曲线显示(`frontend/src/views/Valuation.vue`)

- **按基准重置周期细采样**:FR007 每周、Shibor 3M 每季取一个点(10Y 约 500+ 点),避免 11 个报价点直连的折线感;
- **插值方式可切换(图上方单选)**,两种均严格穿过全部报价点:
  - **零利率线性插值(默认)**——与定价内核同法、两端平推,**图 = 定价所用曲线**;
  - **单调三次 Hermite(Fritsch–Carlson)**——节点切线连续、有弧度,局部极值点切线取 0 保证单调无过冲,两端切线取 0 与平推衔接;与厂商/中债曲线观感一致(中债官方收益率曲线即三次 Hermite 插值,厂商曲线的"弧度"即来源于样条类插值);
- Y 轴 nice 刻度(1/2/5×10^k,约 5~7 格),保证曲线最低点下方有刻度;横轴刻度取报价期限点,短端过密时自动跳过(首末刻度必显)。

### 显示与定价的差异(切 Hermite 时)

- 两种插值在**报价节点处取值完全一致**;线性模式下节点间即定价口径、无差异;
- 切到 Hermite 后,节点之间是视觉平滑,与定价线性插值有约 **0.1~3bp** 的显示差异(tooltip 显示的是显示曲线取值),便于对比两种口径;
- **NPV/DV01 始终不受影响**——定价固定用线性插值,曲线图仅是行情展示;若需定价内核本身升级为 Hermite(彻底中债同款),NPV/DV01 会变化,须重新与厂商口径校准,**当前未做**,属独立决策。

## 数据依赖

运行与测试需要 `data/` 目录下两个 CSV 就位(data/ 不入库属有意决策):

- `rate_value.csv`:估值曲线(按基准/日期的期限点零息利率)
- `rate_info.csv`:期限与定盘信息

`FR007ON行情.csv`、`SHIBOR3M定盘行情.csv` 当前 loader 不读取。
