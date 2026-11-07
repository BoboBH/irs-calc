# 利率互换计算器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单笔人民币利率互换的 Web 计算器:定价(PV/NPV)、现金流明细、平行 DV01 与关键期限 DV01、Campisi 日频归因(白皮书口径)。

**Architecture:** 自研纯函数 Python 计算内核(日历/排期/曲线/定价/风险/归因六模块) + FastAPI 三个接口读 `data/*.csv` 行情 + Vue3/Element Plus 单页前端。无数据库。

**Tech Stack:** Python 3.12(py launcher)、FastAPI、pydantic、pytest、httpx;Vue 3、Element Plus、Vite、axios。

**设计文档:** `docs/specs/2026-11-07-irs-calc-design.md`(口径以它为准)

**运行约定:** 后端一律用项目 venv 解释器 `backend/.venv/Scripts/python.exe -m pytest` / `-m uvicorn`(下文各命令中的 `py -m pytest` 等均按此执行;本机 `python` 是商店占位程序,全局环境禁止装包);Windows Git Bash 环境;PYTHONIOENCODING=utf-8 防中文乱码。

---

## 文件结构(最终形态)

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口 + 静态托管 frontend/dist
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py           # pydantic 请求/响应模型
│   │   ├── services.py          # 请求 → 内核调用的转换层(含错误映射)
│   │   ├── market.py            # GET /api/market
│   │   ├── valuation.py         # POST /api/value
│   │   └── attribution.py       # POST /api/attribution
│   ├── dataio/
│   │   ├── __init__.py
│   │   └── loader.py            # data/*.csv 读取
│   └── core/
│       ├── __init__.py
│       ├── conventions.py       # 基准惯例配置 + year_fraction + tenor 解析
│       ├── calendar.py          # Calendar(交易日历 + 修正顺延)
│       ├── curve.py             # ZeroCurve(DF/插值/远期/扰动)
│       ├── schedule.py          # 排期骨架(固定腿 + FR007周重置 + SHIBOR3M)
│       ├── pricing.py           # 双腿定价 → CashflowRow/LegResult
│       ├── risk.py              # 平行DV01 + KRDV01
│       └── attribution.py       # Campisi 分解
└── tests/
    ├── conftest.py              # 公共夹具(曲线、日历、fixings)
    ├── test_conventions.py
    ├── test_calendar.py
    ├── test_curve.py
    ├── test_schedule.py
    ├── test_pricing.py
    ├── test_risk.py
    ├── test_loader.py
    ├── test_attribution.py
    └── test_api.py
frontend/                        # Task 14 脚手架生成
├── vite.config.js               # 代理 /api → 127.0.0.1:8000
├── src/main.js                  # 挂 Element Plus
├── src/App.vue                  # 挂 Valuation
└── src/views/Valuation.vue      # 全部界面逻辑
```

模块依赖方向:`core` 不依赖任何其他模块;`dataio` 只读 CSV;`api` 依赖 `core + dataio`;前端只碰 `api`。

---

### Task 0: 环境准备

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/` 目录结构(各层 `__init__.py`)

- [ ] **Step 1: 创建目录骨架与依赖清单**

`backend/requirements.txt`:
```
fastapi>=0.115
uvicorn>=0.30
pydantic>=2.7
httpx>=0.27
pytest>=8.0
```

```bash
cd /d/git/irs-calc/backend
mkdir -p app/core app/api app/dataio tests
touch app/__init__.py app/core/__init__.py app/api/__init__.py app/dataio/__init__.py tests/__init__.py
```

- [ ] **Step 2: 安装依赖**

```bash
cd /d/git/irs-calc/backend && py -m pip install -r requirements.txt
```
Expected: 全部安装成功(已有则 skipped)。

- [ ] **Step 3: pytest 冒烟**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: `no tests ran`(收集为空,不报 import 错误)。

- [ ] **Step 4: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "chore: 后端骨架与依赖"
```

---

### Task 1: conventions(基准惯例配置)

**Files:**
- Create: `backend/app/core/conventions.py`
- Test: `backend/tests/test_conventions.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_conventions.py`:
```python
from datetime import date
from app.core.conventions import BENCHMARKS, year_fraction, tenor_to_months


def test_fr007_spec():
    spec = BENCHMARKS["FR007"]
    assert spec.fixing_sec_id == "51,557"
    assert spec.day_count == 365
    assert spec.reset_days == 7
    assert spec.float_pay_months == 3
    assert "1M" in spec.swap_tenors and "10Y" in spec.swap_tenors


def test_shibor3m_spec():
    spec = BENCHMARKS["SHIBOR3M"]
    assert spec.fixing_sec_id == "51,558"
    assert spec.day_count == 360
    assert spec.reset_days is None
    assert "1M" not in spec.swap_tenors and "6M" in spec.swap_tenors


def test_year_fraction_act_365():
    assert year_fraction(date(2026, 6, 1), date(2026, 9, 1), 365) == 92 / 365


def test_year_fraction_act_360():
    assert year_fraction(date(2026, 6, 1), date(2026, 9, 1), 360) == 92 / 360


def test_tenor_to_months():
    assert tenor_to_months("1M") == 1
    assert tenor_to_months("9M") == 9
    assert tenor_to_months("1Y") == 12
    assert tenor_to_months("10Y") == 120
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_conventions.py -v
```
Expected: FAIL(`ModuleNotFoundError: app.core.conventions`)。

- [ ] **Step 3: 实现**

`backend/app/core/conventions.py`:
```python
"""基准利率市场惯例配置(设计文档 §4.3)。"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str              # FR007 / SHIBOR3M
    info_bmk: str          # rate_info.csv 的 BMK_IDX 值
    fixing_sec_id: str     # 定盘序列的 sec_id(注意含千分位逗号)
    day_count: int         # 浮动腿计息基数
    fixed_day_count: int   # 固定腿计息基数
    fixed_freq_months: int  # 固定腿默认付息频率(月)
    float_pay_months: int  # 浮动腿付息频率(月)
    reset_days: int | None  # FR007=7(周重置);SHIBOR3M=None(按期初重置)
    swap_tenors: tuple[str, ...]


BENCHMARKS: dict[str, BenchmarkSpec] = {
    "FR007": BenchmarkSpec(
        name="FR007",
        info_bmk="CNY-FR007",
        fixing_sec_id="51,557",
        day_count=365,
        fixed_day_count=365,
        fixed_freq_months=3,
        float_pay_months=3,
        reset_days=7,
        swap_tenors=("1M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"),
    ),
    "SHIBOR3M": BenchmarkSpec(
        name="SHIBOR3M",
        info_bmk="CNY-SHIBOR-3M",
        fixing_sec_id="51,558",
        day_count=360,
        fixed_day_count=360,
        fixed_freq_months=3,
        float_pay_months=3,
        reset_days=None,
        swap_tenors=("6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"),
    ),
}


def year_fraction(start: date, end: date, day_count: int) -> float:
    """ACT/n 年化计息期限。"""
    return (end - start).days / day_count


def tenor_to_months(tenor: str) -> int:
    """'1M'->1, '9M'->9, '1Y'->12, '10Y'->120。"""
    t = tenor.strip().upper()
    if t.endswith("M"):
        return int(t[:-1])
    if t.endswith("Y"):
        return int(t[:-1]) * 12
    raise ValueError(f"无法解析期限: {tenor!r}")
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_conventions.py -v
```
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 基准惯例配置 FR007/SHIBOR3M"
```

---

### Task 2: calendar(交易日历 + 修正顺延)

**Files:**
- Create: `backend/app/core/calendar.py`
- Test: `backend/tests/test_calendar.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_calendar.py`:
```python
from datetime import date
from app.core.calendar import Calendar

# 用一小段手工构造的交易日:2026-05-25(一)~05-29(五)+ 2026-06-01(一)~06-05(五)
BD = {date(2026, 5, d) for d in range(25, 30)} | {date(2026, 6, d) for d in range(1, 6)}


def test_in_range_business_day():
    cal = Calendar(BD)
    assert cal.is_business_day(date(2026, 5, 25))      # 周一,在数据范围内且为交易日
    assert not cal.is_business_day(date(2026, 5, 30))  # 周六,范围内 → 非交易日


def test_out_of_range_falls_back_to_weekend_rule():
    cal = Calendar(BD)
    # 2026-12-07(周一)在数据范围外 → 按周末规则视为交易日
    assert cal.is_business_day(date(2026, 12, 7))
    assert not cal.is_business_day(date(2026, 12, 6))  # 周日
    assert cal.uses_fallback(date(2026, 12, 7))
    assert not cal.uses_fallback(date(2026, 5, 25))


def test_adjust_modified_following_month_cross_back():
    cal = Calendar(BD)
    # 2026-05-30 周六 → 顺延到 06-01 跨月 → 改往前 05-29(周五)
    assert cal.adjust_modified_following(date(2026, 5, 30)) == date(2026, 5, 29)
    # 2026-06-06 周六 → 顺延到 06-08 周一,未跨月
    assert cal.adjust_modified_following(date(2026, 6, 6)) == date(2026, 6, 8)


def test_adjust_modified_following_month_cross():
    cal = Calendar(BD)
    # 2026-05-31(周日):顺延到 06-01 跨月 → 改为往前到 05-29(周五)
    assert cal.adjust_modified_following(date(2026, 5, 31)) == date(2026, 5, 29)


def test_adjust_business_day_unchanged():
    cal = Calendar(BD)
    assert cal.adjust_modified_following(date(2026, 5, 27)) == date(2026, 5, 27)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_calendar.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现**

`backend/app/core/calendar.py`:
```python
"""交易日历:数据范围内以 FR007 定盘日期为真实交易日;范围外回退周末规则。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


class Calendar:
    def __init__(self, business_days: Iterable[date]):
        days = set(business_days)
        self._bd = days
        self.min_date = min(days)
        self.max_date = max(days)

    def uses_fallback(self, d: date) -> bool:
        """d 是否落在数据覆盖范围之外(该区域日历为周末近似)。"""
        return d < self.min_date or d > self.max_date

    def is_business_day(self, d: date) -> bool:
        if self.uses_fallback(d):
            return d.weekday() < 5
        return d in self._bd

    def next_business_day(self, d: date) -> date:
        nd = d + timedelta(days=1)
        while not self.is_business_day(nd):
            nd += timedelta(days=1)
        return nd

    def prev_business_day(self, d: date) -> date:
        pd = d - timedelta(days=1)
        while not self.is_business_day(pd):
            pd -= timedelta(days=1)
        return pd

    def adjust_modified_following(self, d: date) -> date:
        """修正顺延:下一交易日;若跨月则改为前一交易日。"""
        if self.is_business_day(d):
            return d
        nd = self.next_business_day(d)
        if nd.month != d.month:
            return self.prev_business_day(d)
        return nd
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_calendar.py -v
```
Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 交易日历与修正顺延"
```

---

### Task 3: curve(零息曲线)

**Files:**
- Create: `backend/app/core/curve.py`
- Test: `backend/tests/test_curve.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_curve.py`:
```python
from datetime import date
from app.core.curve import CurvePoint, ZeroCurve

VAL = date(2026, 6, 1)


def make_flat_curve(rate=0.014):
    pts = [
        CurvePoint("6M", date(2026, 12, 1), rate),
        CurvePoint("1Y", date(2027, 6, 1), rate),
        CurvePoint("2Y", date(2028, 6, 1), rate),
    ]
    return ZeroCurve(VAL, pts)


def test_df_at_valuation_is_one():
    assert make_flat_curve().df(VAL) == 1.0


def test_df_formula_simple_compounding():
    # DF = 1/(1+y*tau), tau = ACT/365
    d = date(2026, 9, 1)
    expected = 1 / (1 + 0.014 * 92 / 365)
    assert make_flat_curve().df(d) == expected


def test_df_monotonic_decreasing():
    c = make_flat_curve()
    assert c.df(date(2026, 9, 1)) > c.df(date(2027, 3, 1)) > c.df(date(2028, 6, 1))


def test_zero_rate_interpolation_linear_between_points():
    c = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                        CurvePoint("1Y", date(2027, 6, 1), 0.020)])
    # 2026-12-01 与 2027-06-01 的 τ 中点(线性按 τ 插值)→ 恰为 0.017
    d = date(2027, 3, 1)
    tau_d = (d - VAL).days / 365
    tau_6m = (date(2026, 12, 1) - VAL).days / 365
    tau_1y = (date(2027, 6, 1) - VAL).days / 365
    expected = 0.014 + (0.020 - 0.014) * (tau_d - tau_6m) / (tau_1y - tau_6m)
    assert c.zero_rate(d) == expected


def test_zero_rate_flat_extrapolation():
    c = make_flat_curve(0.014)
    c2 = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                         CurvePoint("1Y", date(2027, 6, 1), 0.020)])
    assert c.zero_rate(date(2027, 9, 1)) == 0.014          # 超末端平推
    assert c2.zero_rate(date(2026, 7, 1)) == 0.014         # 超首端平推


def test_forward_flat_curve_equals_flat_rate():
    """平缓曲线的隐含远期略低于平价利率(单利贴现的结构性结果):

    F = (DF(s)/DF(e) − 1)/τ = y·(τe−τs)/(1+y·τs)/(τe−τs) = y/(1+y·τs)
    """
    c = make_flat_curve(0.014)
    f = c.forward(date(2026, 9, 1), date(2026, 12, 1), 365)
    expected = 0.014 / (1 + 0.014 * 92 / 365)
    # DF 比值路径与闭式路径存在 ~1e-16 的浮点舍入差,不能要求位级相等
    assert abs(f - expected) < 1e-15


def test_shifted_parallel():
    c = make_flat_curve()
    shifted = c.shifted_parallel(1e-4)
    d = date(2026, 9, 1)
    assert shifted.zero_rate(d) == 0.0141
    assert c.zero_rate(d) == 0.014  # 原曲线不变


def test_shifted_keys_triangular_weights():
    c = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                        CurvePoint("1Y", date(2027, 6, 1), 0.014),
                        CurvePoint("2Y", date(2028, 6, 1), 0.014)])
    keys = [p.date for p in c.points]
    # 只在 6M 上 +1bp,1Y 为 0 → 中点(线性按 τ)约抬一半
    shifted = c.shifted_keys(keys, [1e-4, 0.0, 0.0])
    mid = date(2027, 3, 1)
    tau_mid = (mid - VAL).days / 365
    tau_6m = (date(2026, 12, 1) - VAL).days / 365
    tau_1y = (date(2027, 6, 1) - VAL).days / 365
    w = (tau_mid - tau_6m) / (tau_1y - tau_6m)  # 0.4945:τ 上距 6M 的比例(mid 非精确中点)
    # 6M 的三角形权重随 τ 向 1Y 线性衰减:mid 距 6M 90 天/共 182 天 → 权重 = 1-w = 0.5055
    assert abs(shifted.zero_rate(mid) - (0.014 + 1e-4 * (1 - w))) < 1e-15
    # 节点本身
    assert shifted.zero_rate(date(2026, 12, 1)) == 0.0141
    assert shifted.zero_rate(date(2027, 6, 1)) == 0.014


def test_point_dates_and_labels():
    c = make_flat_curve()
    assert c.labels == ["6M", "1Y", "2Y"]
    assert c.point_dates[0] == date(2026, 12, 1)


def test_shifted_keys_rejects_unsorted_key_dates():
    import pytest
    c = make_flat_curve()
    with pytest.raises(ValueError):
        c.shifted_keys([date(2028, 6, 1), date(2026, 12, 1)], [0.0, 1e-4])


def test_constructor_rejects_duplicate_point_dates():
    import pytest
    with pytest.raises(ValueError):
        ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                        CurvePoint("6Mb", date(2026, 12, 1), 0.015)])
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_curve.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现**

`backend/app/core/curve.py`:
```python
"""互换零息曲线:单利贴现 DF=1/(1+y·τ),零利率线性插值,平推外推。

扰动方式(供 DV01):
- shifted_parallel: 全部期限点零利率 +bump
- shifted_keys: 各关键期限点 +bump_k,相邻关键期限之间的点按 τ 线性(三角形)分摊,
  两端外侧取最近关键期限的 bump。平行移动 = 所有 bump_k 相等。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

DAY_COUNT = 365


@dataclass(frozen=True)
class CurvePoint:
    label: str
    date: date
    rate: float  # 小数,如 0.014 = 1.4%


class ZeroCurve:
    def __init__(self, valuation_date: date, points: Sequence[CurvePoint]):
        pts = sorted(points, key=lambda p: p.date)
        if len(pts) < 1:
            raise ValueError("曲线至少需要一个期限点")
        if pts[0].date < valuation_date:
            raise ValueError("期限点日期不能早于估值日")
        for a, b in zip(pts, pts[1:]):
            if a.date == b.date:
                raise ValueError(f"期限点日期重复: {b.date}")
        self.valuation_date = valuation_date
        self.points = pts

    # ---- 内部 ----
    def _tau(self, d: date) -> float:
        return (d - self.valuation_date).days / DAY_COUNT

    @staticmethod
    def _interp_bump(taus: Sequence[float], bumps: Sequence[float], tau: float) -> float:
        """关键期限 bump 按 τ 线性分摊;两端外平推。"""
        if tau <= taus[0]:
            return bumps[0]
        if tau >= taus[-1]:
            return bumps[-1]
        for i in range(len(taus) - 1):
            if taus[i] <= tau <= taus[i + 1]:
                w = (tau - taus[i]) / (taus[i + 1] - taus[i])
                return bumps[i] + (bumps[i + 1] - bumps[i]) * w
        raise AssertionError

    def _shifted(self, key_dates: Sequence[date], bumps: Sequence[float]) -> "ZeroCurve":
        key_taus = [(kd - self.valuation_date).days / DAY_COUNT for kd in key_dates]
        new_points = []
        for p in self.points:
            tau = self._tau(p.date)
            b = self._interp_bump(key_taus, bumps, tau)
            new_points.append(CurvePoint(p.label, p.date, p.rate + b))
        return ZeroCurve(self.valuation_date, new_points)

    # ---- 公开 ----
    @property
    def labels(self) -> list[str]:
        return [p.label for p in self.points]

    @property
    def point_dates(self) -> list[date]:
        return [p.date for p in self.points]

    def shifted_parallel(self, bump: float) -> "ZeroCurve":
        return self._shifted(self.point_dates, [bump] * len(self.points))

    def shifted_keys(self, key_dates: Sequence[date], bumps: Sequence[float]) -> "ZeroCurve":
        if len(key_dates) != len(bumps):
            raise ValueError("key_dates 与 bumps 长度不一致")
        key_taus = [(kd - self.valuation_date).days / DAY_COUNT for kd in key_dates]
        if any(a >= b for a, b in zip(key_taus, key_taus[1:])):
            raise ValueError("key_dates 必须严格递增(按估值日起的 τ)")
        return self._shifted(key_dates, bumps)

    def zero_rate(self, d: date) -> float:
        tau = self._tau(d)
        if tau <= 0:
            return self.points[0].rate
        taus = [self._tau(p.date) for p in self.points]
        rates = [p.rate for p in self.points]
        if tau >= taus[-1]:
            return rates[-1]
        if tau <= taus[0]:
            return rates[0]
        for i in range(len(taus) - 1):
            if taus[i] <= tau <= taus[i + 1]:
                w = (tau - taus[i]) / (taus[i + 1] - taus[i])
                return rates[i] + (rates[i + 1] - rates[i]) * w
        raise AssertionError

    def df(self, d: date) -> float:
        tau = self._tau(d)
        if tau <= 0:
            return 1.0
        return 1.0 / (1.0 + self.zero_rate(d) * tau)

    def forward(self, d1: date, d2: date, day_count: int = DAY_COUNT) -> float:
        if d2 <= d1:
            raise ValueError("forward 需要 d2 > d1")
        tau = (d2 - d1).days / day_count
        return (self.df(d1) / self.df(d2) - 1.0) / tau
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_curve.py -v
```
Expected: 11 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 零息曲线 DF/插值/远期/扰动"
```

---

### Task 4: schedule(排期骨架)

**Files:**
- Create: `backend/app/core/schedule.py`
- Test: `backend/tests/test_schedule.py`

排期只生成**日期骨架**(无利率):付息期(调整后计息起止 + 修正顺延支付日)+ FR007 周 7 天重置子区间 / SHIBOR3M 单一子区间。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_schedule.py`:
```python
from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.schedule import build_fixed_skeleton, build_floating_skeleton

# 2026-05-25 ~ 2026-12-31 中所有工作日视为交易日(测试用简化日历)
BD = set()
d = date(2026, 5, 25)
while d <= date(2026, 12, 31):
    if d.weekday() < 5:
        BD.add(d)
    d = d.fromordinal(d.toordinal() + 1)
CAL = Calendar(BD)


def test_fixed_skeleton_two_quarters():
    sk = build_fixed_skeleton(date(2026, 6, 1), date(2026, 12, 1), 3, CAL)
    assert len(sk.periods) == 2
    p1, p2 = sk.periods
    assert (p1.accrual_start, p1.accrual_end, p1.pay_date) == (
        date(2026, 6, 1), date(2026, 9, 1), date(2026, 9, 1))
    assert (p2.accrual_start, p2.accrual_end, p2.pay_date) == (
        date(2026, 9, 1), date(2026, 12, 1), date(2026, 12, 1))


def test_fixed_skeleton_annual_freq():
    sk = build_fixed_skeleton(date(2026, 6, 1), date(2028, 6, 1), 12, CAL)
    assert len(sk.periods) == 2
    assert sk.periods[0].accrual_end == date(2027, 6, 1)


def test_fixed_skeleton_adjusted_payment():
    # 2026-09-05 是周六 → 付息日顺延到 09-07(周一),未跨月
    sk = build_fixed_skeleton(date(2026, 6, 5), date(2026, 12, 5), 3, CAL)
    assert sk.periods[0].pay_date == date(2026, 9, 7)


def test_fr007_sub_periods_weekly():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(date(2026, 6, 1), date(2026, 12, 1), CAL, spec)
    p1 = sk.periods[0]
    # 06-01 → 09-01 = 92 天 = 13 个整周(91 天) + 1 天末段
    assert len(p1.sub_periods) == 14
    assert p1.sub_periods[0].reset_date == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_start == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_end == date(2026, 6, 8)
    assert p1.sub_periods[1].reset_date == date(2026, 6, 8)
    assert p1.sub_periods[-1].accrual_end == date(2026, 9, 1)
    # 子区间天数之和 = 期间天数
    total = sum((sp.accrual_end - sp.accrual_start).days for sp in p1.sub_periods)
    assert total == 92
    # 子区间首尾相接
    for a, b in zip(p1.sub_periods, p1.sub_periods[1:]):
        assert a.accrual_end == b.accrual_start


def test_shibor3m_single_sub_period():
    spec = BENCHMARKS["SHIBOR3M"]
    sk = build_floating_skeleton(date(2026, 6, 1), date(2026, 12, 1), CAL, spec)
    p1 = sk.periods[0]
    assert len(p1.sub_periods) == 1
    assert p1.sub_periods[0].reset_date == p1.accrual_start == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_end == p1.accrual_end == date(2026, 9, 1)


def test_period_dates_adjusted():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(date(2026, 6, 5), date(2026, 12, 5), CAL, spec)
    p1 = sk.periods[0]
    # 起息日 06-05(周五)调整后仍为自身;期末 09-05(周六)→ 09-07
    assert p1.accrual_start == date(2026, 6, 5)
    assert p1.pay_date == date(2026, 9, 7)
    assert p1.sub_periods[0].reset_date == date(2026, 6, 5)
    assert p1.sub_periods[-1].accrual_end == date(2026, 9, 7)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_schedule.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现**

`backend/app/core/schedule.py`:
```python
"""排期骨架:只生成日期,不含利率。

固定腿:按日历月推进期末日(末端强制为到期日),计息边界与支付日做修正顺延。
浮动腿(FR007):季度期内自调整后起息日每 7 个日历日一个重置子区间,末段截断;
浮动腿(SHIBOR3M):每季度一个子区间,重置日 = 计息期起始日。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec


@dataclass(frozen=True)
class SubPeriodSkeleton:
    reset_date: date
    accrual_start: date
    accrual_end: date


@dataclass(frozen=True)
class PeriodSkeleton:
    accrual_start: date
    accrual_end: date
    pay_date: date
    sub_periods: tuple[SubPeriodSkeleton, ...]


@dataclass(frozen=True)
class ScheduleSkeleton:
    periods: list[PeriodSkeleton]


def add_months(d: date, months: int) -> date:
    """日历月推进,月末日期钳制(如 11-30 +3M = 次年 02-28)。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def _build_periods(effective: date, maturity: date, freq_months: int,
                   calendar: Calendar) -> list[tuple[date, date, date]]:
    """返回 [(调整后 accrual_start, 调整后 accrual_end, 调整后 pay_date)]。"""
    if effective >= maturity:
        raise ValueError("起息日必须早于到期日")
    start_adj = calendar.adjust_modified_following(effective)
    periods = []
    k = freq_months
    while True:
        raw_end = maturity if add_months(effective, k) >= maturity else add_months(effective, k)
        end_adj = calendar.adjust_modified_following(raw_end)
        periods.append((start_adj, end_adj, end_adj))
        if raw_end == maturity:
            break
        start_adj = end_adj
        k += freq_months
    return periods


def build_fixed_skeleton(effective: date, maturity: date, freq_months: int,
                         calendar: Calendar) -> ScheduleSkeleton:
    periods = []
    for s, e, pay in _build_periods(effective, maturity, freq_months, calendar):
        periods.append(PeriodSkeleton(s, e, pay, sub_periods=()))
    return ScheduleSkeleton(periods)


def build_floating_skeleton(effective: date, maturity: date, calendar: Calendar,
                            spec: BenchmarkSpec) -> ScheduleSkeleton:
    periods = []
    for s, e, pay in _build_periods(effective, maturity, spec.float_pay_months, calendar):
        subs = []
        if spec.reset_days is None:  # SHIBOR3M:整段一个子区间
            subs.append(SubPeriodSkeleton(s, s, e))
        else:  # FR007:每 7 个日历日一个子区间,边界不调整,末段截断
            cur = s
            while cur < e:
                nxt = min(cur + timedelta(days=spec.reset_days), e)
                subs.append(SubPeriodSkeleton(cur, cur, nxt))
                cur = nxt
        periods.append(PeriodSkeleton(s, e, pay, sub_periods=tuple(subs)))
    return ScheduleSkeleton(periods)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_schedule.py -v
```
Expected: 6 passed。

- [ ] **Step 5: 运行全部测试确认无回归**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 排期骨架(季度付息/FR007周重置/SHIBOR3M)"
```

---

### Task 5: pricing — 固定腿

**Files:**
- Create: `backend/app/core/pricing.py`(本任务先写固定腿部分)
- Test: `backend/tests/test_pricing.py`(新建)

- [ ] **Step 1: 写失败测试**

`backend/tests/test_pricing.py`:
```python
from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS, year_fraction
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import MissingFixingError, price_fixed_leg
from app.core.schedule import build_fixed_skeleton

VAL = date(2026, 6, 1)
BD = set()
d = date(2025, 1, 1)
while d <= date(2026, 12, 31):
    if d.weekday() < 5:
        BD.add(d)
    d += __import__("datetime").timedelta(days=1)
CAL = Calendar(BD)


def flat_curve(rate=0.014):
    return ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), rate),
                           CurvePoint("1Y", date(2027, 6, 1), rate),
                           CurvePoint("2Y", date(2028, 6, 1), rate)])


def test_fixed_leg_two_periods():
    """6M 互换,季付,平缓曲线 1.4%,固定利率 1.65%,估值日=起息日。

    期1: 06-01→09-01 92天;期2: 09-01→12-01 91天。支付日 DF 均按 DF=1/(1+0.014·τ)。
    """
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    N, K = 100_000_000, 0.0165
    leg = price_fixed_leg(sk, N, K, VAL, flat_curve(), CAL, 365)

    assert len(leg.rows) == 2
    df1 = 1 / (1 + 0.014 * 92 / 365)
    df2 = 1 / (1 + 0.014 * 183 / 365)  # 06-01 → 12-01 共 183 天
    # 先算 τ 再乘,与实现 (notional * rate * year_fraction) 的运算次序一致,避免末位 ULP 差异
    cf1 = N * K * (92 / 365)
    cf2 = N * K * (91 / 365)
    assert leg.rows[0].amount == cf1
    assert leg.rows[0].df == df1
    assert leg.rows[0].pv == cf1 * df1
    assert leg.rows[1].amount == cf2
    assert leg.pv == cf1 * df1 + cf2 * df2


def test_fixed_leg_excludes_past_payments():
    """估值日在第二期期中 → 只剩第二期现金流。"""
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    mid = date(2026, 10, 1)
    # 计划文本的潜在不一致:曲线锚定日必须与定价估值日一致,故此处锚定 mid
    curve = ZeroCurve(mid, [CurvePoint("6M", date(2027, 4, 1), 0.014),
                            CurvePoint("1Y", date(2027, 10, 1), 0.014),
                            CurvePoint("2Y", date(2028, 10, 1), 0.014)])
    leg = price_fixed_leg(sk, 100_000_000, 0.0165, mid, curve, CAL, 365)
    assert len(leg.rows) == 1
    assert leg.rows[0].pay_date == date(2026, 12, 1)


def test_pricing_error_when_curve_before_valuation():
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    old_curve = ZeroCurve(date(2026, 5, 1), [CurvePoint("6M", date(2026, 11, 1), 0.014)])
    # 曲线估值日与定价估值日不一致 → 拒绝,防止静默错价
    try:
        price_fixed_leg(sk, 100_000_000, 0.0165, VAL, old_curve, CAL, 365)
        raise AssertionError("应当抛出 ValueError")
    except ValueError:
        pass


def test_fixed_leg_pay_on_valuation_excluded():
    """ex-coupon 严格边界:支付日 = 估值日的现金流被剔除(该笔进归因 CF 项)。"""
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    v = date(2026, 9, 1)
    curve_v = ZeroCurve(v, [CurvePoint("6M", date(2027, 3, 1), 0.014),
                            CurvePoint("1Y", date(2027, 9, 1), 0.014),
                            CurvePoint("2Y", date(2028, 9, 1), 0.014)])
    leg = price_fixed_leg(sk, 100_000_000, 0.0165, v, curve_v, CAL, 365)
    assert [r.pay_date for r in leg.rows] == [date(2026, 12, 1)]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现(固定腿部分)**

`backend/app/core/pricing.py`:
```python
"""双腿定价。估值口径 ex-coupon:只含支付日在估值日之后的现金流。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec, year_fraction
from app.core.curve import ZeroCurve
from app.core.schedule import PeriodSkeleton, ScheduleSkeleton


class MissingFixingError(ValueError):
    """重置日缺少定盘利率(重置日 ≤ 估值日但序列中没有)。"""


@dataclass
class SubPeriodRow:
    reset_date: date
    accrual_start: date
    accrual_end: date
    days: int
    tau: float
    rate: float
    source: str  # "fixing" | "forward"


@dataclass
class CashflowRow:
    pay_date: date
    accrual_start: date
    accrual_end: date
    days: int
    tau: float
    rate: float
    amount: float
    df: float
    pv: float
    sub_periods: list[SubPeriodRow] = field(default_factory=list)


@dataclass
class LegResult:
    rows: list[CashflowRow]
    pv: float


def _eligible_periods(sk: ScheduleSkeleton, valuation: date) -> list[PeriodSkeleton]:
    return [p for p in sk.periods if p.pay_date > valuation]


def price_fixed_leg(sk: ScheduleSkeleton, notional: float, fixed_rate: float,
                    valuation: date, curve: ZeroCurve, calendar: Calendar,
                    day_count: int) -> LegResult:
    if curve.valuation_date != valuation:
        raise ValueError(f"曲线估值日 {curve.valuation_date} 与定价估值日 {valuation} 不一致")
    rows: list[CashflowRow] = []
    for p in _eligible_periods(sk, valuation):
        tau = year_fraction(p.accrual_start, p.accrual_end, day_count)
        amount = notional * fixed_rate * tau
        df = curve.df(p.pay_date)
        rows.append(CashflowRow(
            pay_date=p.pay_date, accrual_start=p.accrual_start, accrual_end=p.accrual_end,
            days=(p.accrual_end - p.accrual_start).days, tau=tau, rate=fixed_rate,
            amount=amount, df=df, pv=amount * df))
    return LegResult(rows=rows, pv=sum((r.pv for r in rows), 0.0))
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 固定腿定价"
```

---

### Task 6: pricing — 浮动腿(FR007 / SHIBOR3M)

**Files:**
- Modify: `backend/app/core/pricing.py`(追加浮动腿)
- Modify: `backend/tests/test_pricing.py`(追加测试)

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_pricing.py` 末尾追加:
```python
from app.core.pricing import price_floating_leg


def test_floating_fr007_flat_curve():
    """平缓曲线下远期=平价利率1.4%,整个季度按 1.4% 计息。

    浮动 CF = N·(0.014·92/365 + 0) = 3,515,068.49;
    只有 1 期,pay 12-01 前?不——6M 互换第 1 期 pay 在 09-01。
    """
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    N = 100_000_000
    leg = price_floating_leg(sk, N, VAL, flat_curve(), spec, fixings={}, spread=0.0)

    assert len(leg.rows) == 2
    # 第 1 期:首个子区间 reset=06-01=估值日。fixings 为空 → 抛错?
    # 不:估值日当天重置的子区间,估值日 <= reset → 需要 fixing;本测试先给出定盘
```

上面这个用例方向对了但细节繁琐,改为**三个更精确的测试**覆盖全部行为(用下面这段**替换**刚才追加的内容):
```python
from app.core.pricing import price_floating_leg


def test_floating_fr007_forward_only():
    """估值日=起息日,首个子区间 reset=估值日:用定盘 1.35%;其余子区间用隐含远期。

    平缓曲线下第 k 个子区间(重置日距估值日 7k 天)的远期 = 0.014/(1+0.014·7k/365)
    (推导同 test_curve.py::test_forward_flat_curve_equals_flat_rate)。
    """
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    N = 100_000_000
    fixings = {date(2026, 6, 1): 0.0135}
    leg = price_floating_leg(sk, N, VAL, flat_curve(), spec, fixings=fixings, spread=0.0)

    p1 = leg.rows[0]
    assert len(p1.sub_periods) == 14
    assert p1.sub_periods[0].source == "fixing"
    assert p1.sub_periods[0].rate == 0.0135
    assert all(sp.source == "forward" for sp in p1.sub_periods[1:])
    for sp in p1.sub_periods[1:]:
        expected_rate = 0.014 / (1 + 0.014 * (sp.reset_date - VAL).days / 365)
        # DF 比值路径与闭式路径有 ULP 级舍入差(末段 1 天子区间最差 ~8e-14),不能位级相等
        # (同 test_curve.py::test_forward_flat_curve_equals_flat_rate 的容差处理)
        assert abs(sp.rate - expected_rate) < 1e-12
    expected_cf = N * (0.0135 * 7 / 365 + sum(
        (0.014 / (1 + 0.014 * (sp.reset_date - VAL).days / 365))
        * ((sp.accrual_end - sp.accrual_start).days / 365)
        for sp in p1.sub_periods[1:]))
    assert abs(p1.amount - expected_cf) < 1e-6
    df1 = 1 / (1 + 0.014 * 92 / 365)
    assert abs(p1.pv - expected_cf * df1) < 1e-6


def test_floating_fr007_spread_added_on_period_tau():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    leg = price_floating_leg(sk, 100_000_000, VAL, flat_curve(),
                             spec, fixings={date(2026, 6, 1): 0.014}, spread=0.0005)
    base = price_floating_leg(sk, 100_000_000, VAL, flat_curve(),
                              spec, fixings={date(2026, 6, 1): 0.014},
                              spread=0.0).rows[0].amount
    with_spread = leg.rows[0].amount
    # 利差 × 整季 τ(92/365)
    assert abs((with_spread - base) - 100_000_000 * 0.0005 * 92 / 365) < 1e-6


def test_floating_fr007_past_reset_uses_fixing():
    """估值日在期中(06-20):reset≤估值日的子区间用定盘,其余用远期。"""
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    mid = date(2026, 6, 20)
    curve_mid = ZeroCurve(mid, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                                CurvePoint("1Y", date(2027, 6, 1), 0.014),
                                CurvePoint("2Y", date(2028, 6, 1), 0.014)])
    fixings = {date(2026, 6, 1): 0.0135, date(2026, 6, 8): 0.0136}
    leg = price_floating_leg(sk, 100_000_000, mid, curve_mid, spec, fixings=fixings, spread=0.0)
    p1 = leg.rows[0]
    # 计划文本修正:重置网格为 06-01/06-08/06-15/06-22/…,估值日 06-20 时
    # 前 3 个子区间 reset≤估值日 → 定盘;首个远期是 sub[3](reset 06-22)。
    assert p1.sub_periods[0].source == "fixing"
    assert p1.sub_periods[0].rate == 0.0135
    assert p1.sub_periods[1].source == "fixing"
    assert p1.sub_periods[1].rate == 0.0136
    # 06-15 无当日定盘 → 回看取 06-08 的 0.0136(_lookup_fixing 回看分支)
    assert p1.sub_periods[2].source == "fixing"
    assert p1.sub_periods[2].rate == 0.0136
    assert p1.sub_periods[3].source == "forward"


def test_floating_fr007_missing_fixing_raises():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    try:
        price_floating_leg(sk, 100_000_000, VAL, flat_curve(), spec,
                           fixings={}, spread=0.0)
        raise AssertionError("应当抛出 MissingFixingError")
    except MissingFixingError:
        pass


def test_floating_shibor3m_day_count_360():
    """SHIBOR3M:单子区间。reset(06-01)=估值日 → 用定盘 1.4%,按 ACT/360 计息
    CF = N·0.014·92/360(整季 92 天)。"""
    spec = BENCHMARKS["SHIBOR3M"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    fixings = {date(2026, 6, 1): 0.014}
    leg = price_floating_leg(sk, 100_000_000, VAL, flat_curve(), spec,
                             fixings=fixings, spread=0.0)
    p1 = leg.rows[0]
    assert p1.sub_periods[0].source == "fixing"
    expected_cf = 100_000_000 * 0.014 * 92 / 360
    assert abs(p1.amount - expected_cf) < 1e-6
```

注意 `test_floating_fr007_forward_only` 中,平缓曲线的远期恰等于平价利率的前提是**远期计息基数与曲线 τ 基数一致**(均为 365);SHIBOR3M 用例中远期=曲线利率要求曲线 τ 用 365、远期用 360 会出现小差,所以 SHIBOR3M 用例断言用 `1e-6` 容差。

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: FAIL(`ImportError: cannot import name 'price_floating_leg'`)。

- [ ] **Step 3: 实现(追加浮动腿)**

在 `backend/app/core/pricing.py` 末尾追加:
```python
def _lookup_fixing(fixings: dict[date, float], reset_date: date) -> float:
    """取 reset_date 当日或之前最近一条定盘;缺失抛 MissingFixingError。

    有意不设时效上界(设计 §10 口径:定盘按"重置日当日或之前最近"取);
    定盘新鲜度检查与告警由上层(loader / API)负责。
    """
    candidates = [d for d in fixings if d <= reset_date]
    if not candidates:
        raise MissingFixingError(f"缺少重置日 {reset_date} 及之前的定盘利率")
    return fixings[max(candidates)]


def resolve_sub_rate(sp: SubPeriodSkeleton, valuation: date, curve: ZeroCurve, spec: BenchmarkSpec,
                     fixings: dict[date, float]) -> tuple[float, str]:
    """子区间利率:重置日 ≤ 估值日 → 定盘;否则曲线隐含远期。"""
    if sp.reset_date <= valuation:
        return _lookup_fixing(fixings, sp.reset_date), "fixing"
    return curve.forward(sp.accrual_start, sp.accrual_end, spec.day_count), "forward"


def price_floating_leg(sk: ScheduleSkeleton, notional: float, valuation: date,
                       curve: ZeroCurve, spec: BenchmarkSpec,
                       fixings: dict[date, float], spread: float = 0.0) -> LegResult:
    """浮动腿定价:每期 CF = N·(Σ rₖ·τₖ + spread·Στₖ),τₖ 按基准计息惯例;ex-coupon。

    CashflowRow.rate 为指标利率的 τ 加权均值,**不含 spread**(amount 含 spread,
    勿用 rate·τ 重建金额);sub_periods 保留逐子区间明细。
    """
    if curve.valuation_date != valuation:
        raise ValueError(f"曲线估值日 {curve.valuation_date} 与定价估值日 {valuation} 不一致")
    dc = spec.day_count
    rows: list[CashflowRow] = []
    for p in _eligible_periods(sk, valuation):
        sub_rows: list[SubPeriodRow] = []
        acc = 0.0
        total_tau = 0.0
        for sp in p.sub_periods:
            rate, source = resolve_sub_rate(sp, valuation, curve, spec, fixings)
            tau = year_fraction(sp.accrual_start, sp.accrual_end, dc)
            acc += rate * tau
            total_tau += tau
            sub_rows.append(SubPeriodRow(
                reset_date=sp.reset_date, accrual_start=sp.accrual_start,
                accrual_end=sp.accrual_end, days=(sp.accrual_end - sp.accrual_start).days,
                tau=tau, rate=rate, source=source))
        amount = notional * (acc + spread * total_tau)
        df = curve.df(p.pay_date)
        rows.append(CashflowRow(
            pay_date=p.pay_date, accrual_start=p.accrual_start, accrual_end=p.accrual_end,
            days=(p.accrual_end - p.accrual_start).days, tau=total_tau,
            rate=acc / total_tau if total_tau else 0.0,
            amount=amount, df=df, pv=amount * df, sub_periods=sub_rows))
    return LegResult(rows=rows, pv=sum((r.pv for r in rows), 0.0))
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: 9 passed(3 旧 + 5 新浮动 + 1 ex-coupon 边界锁定)。全量套件 36 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 浮动腿定价(FR007周重置定盘/远期,SHIBOR3M)"
```

---

### Task 7: value_swap 组装 + 平价性质测试

**Files:**
- Modify: `backend/app/core/pricing.py`(追加 value_swap)
- Modify: `backend/tests/test_pricing.py`(追加测试)

- [ ] **Step 1: 追加失败测试**

`backend/tests/test_pricing.py` 末尾追加:
```python
from app.core.pricing import value_swap


TRADE = dict(
    benchmark="FR007", direction="receiver", notional=100_000_000,
    fixed_rate=0.0165, spread=0.0,
    effective_date=date(2026, 6, 1), maturity_date=date(2026, 12, 1),
    fixed_freq_months=3,
)


def test_value_swap_receiver_positive_when_k_above_curve():
    res = value_swap(TRADE, VAL, flat_curve(), CAL, BENCHMARKS["FR007"], fixings={date(2026, 6, 1): 0.014})
    assert res["pv_fixed"] > res["pv_floating"]
    assert res["npv"] == res["pv_fixed"] - res["pv_floating"]  # receiver ω=+1


def test_value_swap_payer_flips_sign():
    payer = dict(TRADE, direction="payer")
    res = value_swap(payer, VAL, flat_curve(), CAL, BENCHMARKS["FR007"], fixings={date(2026, 6, 1): 0.014})
    assert res["npv"] == -(res["pv_fixed"] - res["pv_floating"])


def test_par_swap_npv_near_zero():
    """按曲线构造的平价互换 NPV ≈ 0。"""
    spec = BENCHMARKS["FR007"]
    fixings = {date(2026, 6, 1): 0.014}
    curve = flat_curve()
    probe = dict(TRADE, fixed_rate=0.0)
    res0 = value_swap(probe, VAL, curve, CAL, spec, fixings=fixings)
    # 平价率 K* = PV浮动 / (N·Στᵢ·DFᵢ)
    tau_df = 0.0
    for r in res0["fixed_rows"]:
        tau_df += r.tau * r.df
    k_star = res0["pv_floating"] / (100_000_000 * tau_df)
    par = dict(TRADE, fixed_rate=k_star)
    res = value_swap(par, VAL, curve, CAL, spec, fixings=fixings)
    assert abs(res["npv"]) < 1e-4
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: FAIL(`ImportError: cannot import name 'value_swap'`)。

- [ ] **Step 3: 实现(追加 value_swap)**

`backend/app/core/pricing.py` 末尾追加:
```python
def value_swap(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
               spec: BenchmarkSpec, *, fixings: dict[date, float]) -> dict:
    """整笔互换估值。

    trade 键:benchmark/direction/notional/fixed_rate/spread/effective_date/
    maturity_date/fixed_freq_months(direction: receiver|payer,receiver=收固定 ω=+1)。
    返回 dict:npv/pv_fixed/pv_floating/fixed_rows/floating_rows。
    """
    fixed_freq = trade.get("fixed_freq_months", spec.fixed_freq_months)
    sk_fix = build_fixed_skeleton(trade["effective_date"], trade["maturity_date"],
                                  fixed_freq, calendar)
    sk_flt = build_floating_skeleton(trade["effective_date"], trade["maturity_date"],
                                     calendar, spec)
    leg_fix = price_fixed_leg(sk_fix, trade["notional"], trade["fixed_rate"],
                              valuation, curve, calendar, spec.fixed_day_count)
    leg_flt = price_floating_leg(sk_flt, trade["notional"], valuation, curve, spec,
                                 fixings=fixings, spread=trade.get("spread", 0.0))
    omega = 1.0 if trade["direction"] == "receiver" else -1.0
    return {
        "npv": omega * (leg_fix.pv - leg_flt.pv),
        "pv_fixed": leg_fix.pv,
        "pv_floating": leg_flt.pv,
        "omega": omega,
        "fixed_rows": leg_fix.rows,
        "floating_rows": leg_flt.rows,
    }
```

并在 `backend/app/core/pricing.py` 顶部 import 区补一行:
```python
from app.core.schedule import build_fixed_skeleton, build_floating_skeleton, ScheduleSkeleton
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: 12 passed(9 旧 + 3 新;全量套件 39 passed)。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): value_swap 组装与平价性质测试"
```

---

### Task 8: risk(平行 DV01 + KRDV01)

**Files:**
- Create: `backend/app/core/risk.py`
- Test: `backend/tests/test_risk.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_risk.py`:
```python
from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import value_swap
from app.core.risk import key_tenors_for, krdv01, parallel_dv01

VAL = date(2026, 6, 1)
BD = set()
d = date(2025, 1, 1)
while d <= date(2026, 12, 31):
    if d.weekday() < 5:
        BD.add(d)
    d += __import__("datetime").timedelta(days=1)
CAL = Calendar(BD)

TRADE = dict(
    benchmark="FR007", direction="receiver", notional=100_000_000,
    fixed_rate=0.0165, spread=0.0,
    effective_date=VAL, maturity_date=date(2028, 6, 1),
    fixed_freq_months=3,
)
FIXINGS = {date(2026, 6, 1): 0.014}


def curve_two_year():
    pts = [CurvePoint(t, d, 0.014) for t, d in [
        ("1M", date(2026, 7, 1)), ("3M", date(2026, 9, 1)),
        ("6M", date(2026, 12, 1)), ("9M", date(2027, 3, 1)),
        ("1Y", date(2027, 6, 1)), ("2Y", date(2028, 6, 1))]]
    return ZeroCurve(VAL, pts)


def test_parallel_dv01_receiver_negative():
    """收固定:利率↑ → NPV↓,DV01 为负。"""
    dv = parallel_dv01(TRADE, VAL, curve_two_year(), CAL, BENCHMARKS["FR007"], fixings=FIXINGS)
    assert dv < 0


def test_krdv01_sums_to_parallel_dv01():
    """白皮书性质:关键期限三角形权重扰动下 Σ KRDV01ₖ = 平行 DV01。"""
    spec = BENCHMARKS["FR007"]
    curve = curve_two_year()
    keys = key_tenors_for(curve, TRADE["maturity_date"])
    parts = krdv01(TRADE, VAL, curve, CAL, spec, fixings=FIXINGS, key_tenors=keys)
    total = sum(x["dv01"] for x in parts)
    dv = parallel_dv01(TRADE, VAL, curve, CAL, spec, fixings=FIXINGS)
    assert abs(total - dv) < 1e-6


def test_key_tenors_filtered_by_maturity():
    """2Y 互换只保留日期 ≤ 到期日的期限点。"""
    keys = key_tenors_for(curve_two_year(), date(2026, 12, 1))
    assert [d for _, d in keys] == [date(2026, 7, 1), date(2026, 9, 1), date(2026, 12, 1)]
    assert [t for t, _ in keys] == ["1M", "3M", "6M"]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_risk.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现**

`backend/app/core/risk.py`:
```python
"""风险指标:平行 DV01 与关键期限 DV01(白皮书 §曲线效应)。

约定(白皮书符号):DV01 = 利率上升 1bp 时现值的变动(含头寸方向);
KRDV01ₖ 在当前估值日、以当前曲线为基准,对单个关键期限 +1bp(三角形分摊)计算。
"""
from __future__ import annotations

from datetime import date

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec
from app.core.curve import ZeroCurve
from app.core.pricing import value_swap

BUMP = 1e-4  # 1bp


def key_tenors_for(curve: ZeroCurve, maturity: date) -> list[tuple[str, date]]:
    """关键期限集合:仅保留覆盖剩余期限所需的期限点(日期 ≤ 到期日)。"""
    return [(p.label, p.date) for p in curve.points if p.date <= maturity]


def _npv_with_curve(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
                    spec: BenchmarkSpec, fixings: dict[date, float]) -> float:
    return value_swap(trade, valuation, curve, calendar, spec, fixings=fixings)["npv"]


def parallel_dv01(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
                  spec: BenchmarkSpec, *, fixings: dict[date, float]) -> float:
    bumped = curve.shifted_parallel(BUMP)
    return _npv_with_curve(trade, valuation, bumped, calendar, spec, fixings) \
        - _npv_with_curve(trade, valuation, curve, calendar, spec, fixings)


def krdv01(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
           spec: BenchmarkSpec, *, fixings: dict[date, float],
           key_tenors: list[tuple[str, date]]) -> list[dict]:
    base = _npv_with_curve(trade, valuation, curve, calendar, spec, fixings)
    key_dates = [d for _, d in key_tenors]
    out = []
    for i, (label, kd) in enumerate(key_tenors):
        bumps = [0.0] * len(key_dates)
        bumps[i] = BUMP
        bumped = curve.shifted_keys(key_dates, bumps)
        npv_b = _npv_with_curve(trade, valuation, bumped, calendar, spec, fixings)
        out.append({"tenor": label, "date": kd, "dv01": npv_b - base})
    return out
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_risk.py -v
```
Expected: 3 passed。

- [ ] **Step 5: 运行全部测试**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): 平行DV01与关键期限DV01"
```

---

### Task 9: dataio/loader(读取真实行情文件)

**Files:**
- Create: `backend/app/dataio/loader.py`
- Test: `backend/tests/test_loader.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_loader.py`:
```python
from datetime import date
import pytest
from app.core.conventions import BENCHMARKS
from app.dataio.loader import (MarketDataError, build_calendar, curve_for,
                               fixings_for, load_instruments, load_value_rows)


def test_load_value_rows_parses_comma_secid_and_percent():
    rows = load_value_rows()
    # sec_id 含千分位逗号,按字符串键;value 为百分数 → 小数
    assert rows["51,557"][date(2026, 11, 6)] == pytest.approx(0.014)
    assert len(rows["51,557"]) == 457


def test_load_instruments():
    ins = load_instruments()
    fr = [i for i in ins if i["bmk"] == "CNY-FR007"]
    assert len(fr) == 11
    assert any(i["tenor"] == "10Y" and i["sec_id"] == "249,305" for i in fr)


def test_curve_for_fr007_20261106():
    pts = curve_for("FR007", date(2026, 11, 6))
    assert [p.label for p in pts] == list(BENCHMARKS["FR007"].swap_tenors)
    assert pts[0].label == "1M"
    assert pts[0].rate == pytest.approx(0.013838)
    assert pts[0].date == date(2026, 7, 6)      # 估值日 + 1M
    assert pts[-1].label == "10Y"
    assert pts[-1].rate == pytest.approx(0.019)


def test_curve_for_shibor3m():
    pts = curve_for("SHIBOR3M", date(2026, 11, 6))
    assert len(pts) == 9
    assert pts[0].label == "6M"


def test_curve_for_missing_date_raises():
    with pytest.raises(MarketDataError):
        curve_for("FR007", date(2024, 1, 1))


def test_fixings_for_fr007_and_shibor3m():
    fx = fixings_for("FR007")
    assert len(fx) == 457
    assert fx[date(2025, 1, 2)] == pytest.approx(0.018)
    assert fx[date(2026, 11, 6)] == pytest.approx(0.014)
    fx2 = fixings_for("SHIBOR3M")
    assert fx2[date(2026, 11, 6)] == pytest.approx(0.01398)


def test_build_calendar_from_fr007_fixing_dates():
    cal = build_calendar()
    assert cal.is_business_day(date(2026, 11, 6))    # 周五,有定盘
    assert not cal.is_business_day(date(2026, 11, 7))  # 周六
    assert cal.uses_fallback(date(2027, 1, 1))       # 数据范围外
    assert not cal.uses_fallback(date(2026, 11, 6))
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_loader.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 3: 实现**

`backend/app/dataio/loader.py`:
```python
"""读取 data/ 目录行情文件。

格式约定(与现有文件一致):
- rate_value.csv: Tab 分隔,列 sec_id|date|value;sec_id 含千分位逗号(字符串原样);
  value 为百分数(如 1.3838 → 0.013838)
- rate_info.csv: 列 sec_id|name|sec_code|BMK_IDX|tenor
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS, BenchmarkSpec, tenor_to_months
from app.core.curve import CurvePoint
from app.core.schedule import add_months

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class MarketDataError(ValueError):
    """行情数据缺失或无法解析。"""


def load_value_rows(path: Path | None = None) -> dict[str, dict[date, float]]:
    """返回 {sec_id: {date: rate小数}}。"""
    p = path or (DATA_DIR / "rate_value.csv")
    out: dict[str, dict[date, float]] = {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # 表头
        for sec_id, d, v in reader:
            key = sec_id.strip()
            out.setdefault(key, {})[date.fromisoformat(d)] = float(v) / 100.0
    return out


def load_instruments(path: Path | None = None) -> list[dict]:
    """返回 [{sec_id, name, sec_code, bmk, tenor}]。"""
    p = path or (DATA_DIR / "rate_info.csv")
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for sec_id, name, sec_code, bmk, tenor in reader:
            out.append({"sec_id": sec_id.strip(), "name": name.strip(),
                        "sec_code": sec_code.strip(), "bmk": bmk.strip(),
                        "tenor": tenor.strip()})
    return out


def _tenor_sec_ids(instruments: list[dict], spec: BenchmarkSpec) -> dict[str, str]:
    """该基准下 tenor → sec_id 映射。"""
    m = {i["tenor"]: i["sec_id"] for i in instruments if i["bmk"] == spec.info_bmk}
    missing = set(spec.swap_tenors) - set(m)
    if missing:
        raise MarketDataError(f"{spec.name} 品种表缺少期限: {sorted(missing)}")
    return m


def curve_for(benchmark: str, valuation_date: date) -> list[CurvePoint]:
    """按估值日 + 品种表期限构建曲线点(日期 = 估值日 + 期限)。"""
    spec = BENCHMARKS[benchmark]
    rows = load_value_rows()
    sec_map = _tenor_sec_ids(load_instruments(), spec)
    points = []
    for tenor in spec.swap_tenors:
        sec_id = sec_map[tenor]
        series = rows.get(sec_id, {})
        if valuation_date not in series:
            raise MarketDataError(f"{spec.name} 期限 {tenor} 在 {valuation_date} 无行情")
        points.append(CurvePoint(tenor, add_months(valuation_date, tenor_to_months(tenor)),
                                 series[valuation_date]))
    return points


def fixings_for(benchmark: str) -> dict[date, float]:
    spec = BENCHMARKS[benchmark]
    return load_value_rows().get(spec.fixing_sec_id, {})


def build_calendar() -> Calendar:
    """交易日历 = FR007 定盘有值的日期(银行间真实交易日)。"""
    days = fixings_for("FR007")
    if not days:
        raise MarketDataError("FR007 定盘序列为空,无法构建交易日历")
    return Calendar(set(days))
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_loader.py -v
```
Expected: 7 passed。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(dataio): 行情/定盘/品种表加载与交易日历构建"
```

---

### Task 10: attribution(Campisi 归因)+ 定价函数扩展

归因需要定价器支持两个新参数(均为可选、默认不变,向后兼容):

- `fixing_cutoff`:静态曲线情景用——重置日 ≤ cutoff 才用定盘,(cutoff, 估值日] 之间的重置改用曲线隐含远期(白皮书"静态曲线下新一期浮动利率按隐含远期确定")
- `min_pay_date`:现金流统计用——把"只含支付日 > 估值日"的过滤改为"支付日 > min_pay_date"

**Files:**
- Modify: `backend/app/core/pricing.py`(三个函数加参数)
- Modify: `backend/app/core/risk.py`(krdv01/parallel_dv01 加 fixing_cutoff)
- Create: `backend/app/core/attribution.py`
- Modify: `backend/tests/test_pricing.py`(cutoff 单测)
- Test: `backend/tests/test_attribution.py`(新建)

- [ ] **Step 1: 在 test_pricing.py 追加 cutoff 失败测试**

```python
def test_floating_fixing_cutoff_uses_forward_after_cutoff():
    """静态曲线情景:估值日 06-20、cutoff=06-01 → reset 06-01 用定盘,06-08 起走远期。"""
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(VAL, date(2026, 12, 1), CAL, spec)
    mid = date(2026, 6, 20)
    curve_mid = ZeroCurve(mid, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                                CurvePoint("1Y", date(2027, 6, 1), 0.014),
                                CurvePoint("2Y", date(2028, 6, 1), 0.014)])
    fixings = {date(2026, 6, 1): 0.0135, date(2026, 6, 8): 0.0136}
    leg = price_floating_leg(sk, 100_000_000, mid, curve_mid, spec,
                             fixings=fixings, spread=0.0, fixing_cutoff=date(2026, 6, 1))
    subs = leg.rows[0].sub_periods
    assert subs[0].source == "fixing"
    assert subs[1].source == "forward"      # cutoff 之后不看真实定盘
    assert subs[1].rate != 0.0136


def test_min_pay_date_window_for_cf():
    """min_pay_date=t0、估值日=t1:返回支付日 > t0 的现金流(归因 CF 窗口用)。"""
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    t1 = date(2026, 9, 15)
    curve_t1 = ZeroCurve(t1, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                              CurvePoint("1Y", date(2027, 6, 1), 0.014),
                              CurvePoint("2Y", date(2028, 6, 1), 0.014)])
    leg = price_fixed_leg(sk, 100_000_000, 0.0165, t1, curve_t1, CAL, 365,
                          min_pay_date=date(2026, 9, 1))
    assert [r.pay_date for r in leg.rows] == [date(2026, 12, 1)]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py -v
```
Expected: FAIL(`TypeError: ... unexpected keyword argument 'fixing_cutoff'`)。

- [ ] **Step 3: 修改 pricing.py**

`price_fixed_leg` 签名改为(函数体只改两处标注行):
```python
def price_fixed_leg(sk: ScheduleSkeleton, notional: float, fixed_rate: float,
                    valuation: date, curve: ZeroCurve, calendar: Calendar,
                    day_count: int, min_pay_date: date | None = None) -> LegResult:
```
过滤行改为:
```python
    cutoff = min_pay_date or valuation
    # for p in sk.periods if p.pay_date > cutoff ...
```
即 `_eligible_periods` 改为:
```python
def _eligible_periods(sk: ScheduleSkeleton, valuation: date,
                      min_pay_date: date | None = None) -> list[PeriodSkeleton]:
    cutoff = min_pay_date or valuation
    return [p for p in sk.periods if p.pay_date > cutoff]
```
`price_fixed_leg` 内循环改为 `for p in _eligible_periods(sk, valuation, min_pay_date):`。

`resolve_sub_rate` 改为:
```python
def resolve_sub_rate(sp, valuation: date, curve: ZeroCurve, spec: BenchmarkSpec,
                     fixings: dict[date, float],
                     fixing_cutoff: date | None = None) -> tuple[float, str]:
    """子区间利率:重置日 ≤ cutoff(默认=估值日)→ 定盘;否则曲线隐含远期。"""
    cutoff = fixing_cutoff or valuation
    if sp.reset_date <= cutoff:
        return _lookup_fixing(fixings, sp.reset_date), "fixing"
    return curve.forward(sp.accrual_start, sp.accrual_end, spec.day_count), "forward"
```

`price_floating_leg` 签名与循环改为:
```python
def price_floating_leg(sk: ScheduleSkeleton, notional: float, valuation: date,
                       curve: ZeroCurve, spec: BenchmarkSpec,
                       fixings: dict[date, float], spread: float = 0.0,
                       min_pay_date: date | None = None,
                       fixing_cutoff: date | None = None) -> LegResult:
```
```python
    for p in _eligible_periods(sk, valuation, min_pay_date):
        ...
            rate, source = resolve_sub_rate(sp, valuation, curve, spec, fixings,
                                            fixing_cutoff)
```

`value_swap` 签名与内部调用改为:
```python
def value_swap(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
               spec: BenchmarkSpec, *, fixings: dict[date, float],
               min_pay_date: date | None = None,
               fixing_cutoff: date | None = None) -> dict:
```
```python
    leg_fix = price_fixed_leg(sk_fix, trade["notional"], trade["fixed_rate"],
                              valuation, curve, calendar, spec.fixed_day_count,
                              min_pay_date=min_pay_date)
    leg_flt = price_floating_leg(sk_flt, trade["notional"], valuation, curve, spec,
                                 fixings=fixings, spread=trade.get("spread", 0.0),
                                 min_pay_date=min_pay_date, fixing_cutoff=fixing_cutoff)
```

- [ ] **Step 4: 修改 risk.py**

`parallel_dv01` 与 `krdv01` 均加关键字参数 `fixing_cutoff: date | None = None`,内部 `_npv_with_curve` 透传:
```python
def _npv_with_curve(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
                    spec: BenchmarkSpec, fixings: dict[date, float],
                    fixing_cutoff: date | None = None) -> float:
    return value_swap(trade, valuation, curve, calendar, spec, fixings=fixings,
                      fixing_cutoff=fixing_cutoff)["npv"]
```

- [ ] **Step 5: 运行 pricing/risk 全部测试确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_pricing.py tests/test_risk.py -v
```
Expected: 11 + 3 passed(新 2 个也通过)。

- [ ] **Step 6: 写归因失败测试**

`backend/tests/test_attribution.py`:
```python
from datetime import date, timedelta
import pytest
from app.core.attribution import run_attribution, static_curve
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.curve import CurvePoint, ZeroCurve
from app.core.schedule import add_months

VAL = date(2026, 6, 1)
T1 = date(2026, 6, 8)
BD = set()
d = date(2025, 1, 1)
while d <= date(2028, 12, 31):
    if d.weekday() < 5:
        BD.add(d)
    d += timedelta(days=1)
CAL = Calendar(BD)

TRADE = dict(
    benchmark="FR007", direction="receiver", notional=100_000_000,
    fixed_rate=0.0165, spread=0.0,
    effective_date=VAL, maturity_date=date(2028, 6, 1),
    fixed_freq_months=3,
)
FIXINGS = {VAL: 0.014}


def curve_asof(v: date, rate: float) -> ZeroCurve:
    pts = [CurvePoint(t, add_months(v, m), rate)
           for t, m in [("6M", 6), ("1Y", 12), ("2Y", 24)]]
    return ZeroCurve(v, pts)


def test_static_curve_same_rates_as_of_t1():
    c0 = curve_asof(VAL, 0.014)
    st = static_curve(c0, T1)
    assert st.valuation_date == T1
    assert [p.label for p in st.points] == ["6M", "1Y", "2Y"]
    assert [p.date for p in st.points] == [date(2026, 12, 8), date(2027, 6, 8), date(2028, 6, 8)]
    assert [p.rate for p in st.points] == [0.014, 0.014, 0.014]


def test_attribution_identity_and_carry():
    """t0→t1 = 1 周(无付息)。曲线 1.4%→1.5% 平行上移 10bp。

    - CF = 0(区间内无支付日)
    - Carry = ω·N·(K − L0)·7/365(固定/浮动计息基数均 365)
    - Δy 每个关键期限恰为 10bp
    - 勾稽:Θ + Curve + ε = ΔNPV(ε 由定义保证,identity 校验浮点一致性)
    """
    spec = BENCHMARKS["FR007"]
    res = run_attribution(
        trade=TRADE, start_date=VAL, end_date=T1,
        curve_t0=curve_asof(VAL, 0.014), curve_t1=curve_asof(T1, 0.015),
        fixings=FIXINGS, calendar=CAL, spec=spec)

    assert res.cf == 0.0
    assert res.delta_npv == pytest.approx(res.npv_t1 - res.npv_t0)
    assert res.carry == pytest.approx(100_000_000 * (0.0165 - 0.014) * 7 / 365)
    assert res.roll == pytest.approx(res.theta - res.carry)
    assert res.theta == pytest.approx(res.npv_static + res.cf - res.npv_t0)
    assert all(abs(x["dy_bp"] - 10.0) < 1e-9 for x in res.detail)
    assert res.curve_effect == pytest.approx(sum(x["contribution"] for x in res.detail))
    assert res.residual == pytest.approx(res.delta_npv - res.theta - res.curve_effect)
    assert res.spread == 0.0
    assert res.identity_ok
    assert abs(res.identity_diff) < 1e-6
    # 收固定 + 利率上行 → 曲线效应为负
    assert res.curve_effect < 0


def test_attribution_cf_counts_payment_in_window():
    """起息日 06-05(周五),t0=06-05、t1=09-08:第一期支付日 09-05(周六)顺延
    至 09-07,落在 (t0,t1] → CF 进全价损益。

    t1 估值需要 ≤ t1 的全部周定盘:Q1 重置 06-05+7k(k=0..13,至 09-04)
    以及 Q2 首个重置 09-07(调整后期初)。
    """
    spec = BENCHMARKS["FR007"]
    trade = dict(TRADE, effective_date=date(2026, 6, 5))
    fixings = {date(2026, 6, 5) + timedelta(days=7 * k): 0.014 for k in range(14)}
    fixings[date(2026, 9, 7)] = 0.014
    res = run_attribution(
        trade=trade, start_date=date(2026, 6, 5), end_date=date(2026, 9, 8),
        curve_t0=curve_asof(date(2026, 6, 5), 0.014),
        curve_t1=curve_asof(date(2026, 9, 8), 0.014),
        fixings=fixings, calendar=CAL, spec=spec)
    # 曲线不动 → ΔNPV = CF(唯一变动是时间流逝 + 现金流支付)
    assert res.cf > 0
    assert res.delta_npv == pytest.approx(res.npv_t1 + res.cf - res.npv_t0)
    assert res.identity_ok
```

- [ ] **Step 7: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_attribution.py -v
```
Expected: FAIL(模块不存在)。

- [ ] **Step 8: 实现**

`backend/app/core/attribution.py`:
```python
"""Campisi 日频归因(白皮书 §Campisi 归因框架,公式逐条落地)。

分解路径:先时间(静态曲线推进至 t1)、后曲线(在 (t1; C̃_t1) 处一阶展开)。
恒等式:ΔNPV = Θ + Curve + Spread + ε,Spread 恒为 0(单曲线)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec, tenor_to_months, year_fraction
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import _lookup_fixing, value_swap
from app.core.risk import krdv01, key_tenors_for
from app.core.schedule import add_months, build_floating_skeleton


@dataclass
class AttributionResult:
    delta_npv: float
    cf: float
    npv_t0: float
    npv_t1: float
    npv_static: float
    theta: float
    carry: float
    roll: float
    curve_effect: float
    spread: float
    residual: float
    detail: list[dict] = field(default_factory=list)
    identity_ok: bool = False
    identity_diff: float = 0.0
    warnings: list[str] = field(default_factory=list)


def static_curve(curve_t0: ZeroCurve, valuation_t1: date) -> ZeroCurve:
    """静态曲线 C̃_t1:各期限零息利率与 t0 相同,估值日推进至 t1。"""
    pts = [CurvePoint(p.label, add_months(valuation_t1, tenor_to_months(p.label)), p.rate)
           for p in curve_t0.points]
    return ZeroCurve(valuation_t1, pts)


def _zero_at(curve: ZeroCurve, label: str) -> float:
    """曲线在其 label 期限上的零息利率(constant maturity 口径)。"""
    return curve.zero_rate(add_months(curve.valuation_date, tenor_to_months(label)))


def _current_reset_fixing(trade: dict, calendar: Calendar, spec: BenchmarkSpec,
                          fixings: dict[date, float], t0: date) -> float:
    """L0:t0 所在重置子区间重置日的已定盘利率(白皮书 §票息效应)。"""
    sk = build_floating_skeleton(trade["effective_date"], trade["maturity_date"],
                                 calendar, spec)
    for p in sk.periods:
        for sp in p.sub_periods:
            if sp.accrual_start <= t0 < sp.accrual_end:
                return _lookup_fixing(fixings, sp.reset_date)
    return _lookup_fixing(fixings, t0)


def run_attribution(*, trade: dict, start_date: date, end_date: date,
                    curve_t0: ZeroCurve, curve_t1: ZeroCurve,
                    fixings: dict[date, float], calendar: Calendar,
                    spec: BenchmarkSpec) -> AttributionResult:
    omega = 1.0 if trade["direction"] == "receiver" else -1.0
    N = trade["notional"]
    s = trade.get("spread", 0.0)

    # 1. 全价重估
    npv_t0 = value_swap(trade, start_date, curve_t0, calendar, spec, fixings=fixings)["npv"]
    npv_t1 = value_swap(trade, end_date, curve_t1, calendar, spec, fixings=fixings)["npv"]

    # 2. CF(t0,t1]:金额按实际定盘计(reset ≤ t1 均已知),取支付日 ∈ (t0, t1]
    cf_res = value_swap(trade, end_date, curve_t1, calendar, spec, fixings=fixings,
                        min_pay_date=start_date)
    cf = omega * (
        sum(r.amount for r in cf_res["fixed_rows"] if r.pay_date <= end_date)
        - sum(r.amount for r in cf_res["floating_rows"] if r.pay_date <= end_date))
    delta_npv = npv_t1 + cf - npv_t0

    # 3. 时间效应:静态曲线推进
    st = static_curve(curve_t0, end_date)
    npv_static = value_swap(trade, end_date, st, calendar, spec, fixings=fixings,
                            fixing_cutoff=start_date)["npv"]
    theta = npv_static + cf - npv_t0

    # 4. 票息效应
    tau_fix = year_fraction(start_date, end_date, spec.fixed_day_count)
    tau_flt = 0.0
    sk_flt = build_floating_skeleton(trade["effective_date"], trade["maturity_date"],
                                     calendar, spec)
    for p in sk_flt.periods:
        for sp in p.sub_periods:
            a = max(sp.accrual_start, start_date)
            b = min(sp.accrual_end, end_date)
            if b > a:
                tau_flt += year_fraction(a, b, spec.day_count)
    l0 = _current_reset_fixing(trade, calendar, spec, fixings, start_date)
    carry = omega * N * (trade["fixed_rate"] * tau_fix - (l0 + s) * tau_flt)

    # 5. 骑乘 = 轧差;6. 曲线效应(KRDV01 在 (t1; C̃_t1) 处,cutoff=t0 与 Θ 衔接)
    roll = theta - carry
    keys = key_tenors_for(st, trade["maturity_date"])
    parts = krdv01(trade, end_date, st, calendar, spec, fixings=fixings,
                   key_tenors=keys, fixing_cutoff=start_date)
    detail = []
    curve_effect = 0.0
    for x in parts:
        dy = _zero_at(curve_t1, x["tenor"]) - _zero_at(curve_t0, x["tenor"])
        dy_bp = dy * 1e4
        contribution = x["dv01"] * dy_bp
        curve_effect += contribution
        detail.append({"tenor": x["tenor"], "dy_bp": dy_bp,
                       "krdv01": x["dv01"], "contribution": contribution})

    # 7. 残差与勾稽
    spread = 0.0
    residual = delta_npv - theta - curve_effect - spread
    total = theta + curve_effect + spread + residual
    identity_diff = abs(total - delta_npv)
    warnings = []
    if not keys:
        warnings.append("关键期限集合为空:剩余期限不足最小期限点,曲线效应为 0")

    return AttributionResult(
        delta_npv=delta_npv, cf=cf, npv_t0=npv_t0, npv_t1=npv_t1,
        npv_static=npv_static, theta=theta, carry=carry, roll=roll,
        curve_effect=curve_effect, spread=spread, residual=residual,
        detail=detail, identity_ok=identity_diff < 1e-6,
        identity_diff=identity_diff, warnings=warnings)
```

同时给 `backend/app/core/risk.py` 的 `krdv01` 加 `fixing_cutoff` 透传(与 `_npv_with_curve` 一致):
```python
    for i, (label, kd) in enumerate(key_tenors):
        bumps = [0.0] * len(key_dates)
        bumps[i] = BUMP
        bumped = curve.shifted_keys(key_dates, bumps)
        npv_b = _npv_with_curve(trade, valuation, bumped, calendar, spec, fixings,
                                fixing_cutoff)
        out.append({"tenor": label, "date": kd, "dv01": npv_b - base})
```
(`base` 同样用 `fixing_cutoff` 计算。)

注意:静态曲线点日期用 `add_months(t1, tenor月数)` 重算——若某 label 在 curve_t0 中本不存在也无妨,static_curve 以 curve_t0 的点集为准。

- [ ] **Step 9: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_attribution.py -v
```
Expected: 3 passed。

- [ ] **Step 10: 全量回归**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: 全部通过。

- [ ] **Step 11: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(core): Campisi 归因(Θ/Carry/Roll/Curve/ε)与勾稽校验"
```

---

### Task 11: API — 日志、schemas、market 接口

**Files:**
- Create: `backend/app/logging_setup.py`(滚动日志:按天 + 50MB,保留 7 天,全局单 handler)
- Create: `backend/app/api/schemas.py`
- Create: `backend/app/api/services.py`
- Create: `backend/app/api/market.py`
- Modify: `backend/app/main.py`(新建入口)
- Test: `backend/tests/test_api.py`(新建)

- [ ] **Step 1: 写失败测试**

`backend/tests/test_api.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_market_fr007():
    r = client.get("/api/market", params={"benchmark": "FR007", "date": "2026-11-06"})
    assert r.status_code == 200
    body = r.json()
    assert body["benchmark"] == "FR007"
    assert body["valuation_date"] == "2026-11-06"
    assert len(body["curve"]) == 11
    assert body["curve"][0] == {"tenor": "1M", "rate": 1.3838}      # 接口层用百分数
    assert body["fixing"]["date"] == "2026-11-06"
    assert body["fixing"]["rate"] == pytest.approx(1.4)


def test_market_shibor3m():
    r = client.get("/api/market", params={"benchmark": "SHIBOR3M", "date": "2026-11-06"})
    assert r.status_code == 200
    assert len(r.json()["curve"]) == 9


def test_market_missing_date_404():
    r = client.get("/api/market", params={"benchmark": "FR007", "date": "2024-01-01"})
    assert r.status_code == 404
    assert "无行情" in r.json()["detail"]


def test_market_bad_benchmark_422():
    r = client.get("/api/market", params={"benchmark": "SOFR", "date": "2026-11-06"})
    assert r.status_code == 422
```

(文件顶部补 `import pytest`。)

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_api.py -v
```
Expected: FAIL(`ModuleNotFoundError: app.main`)。

- [ ] **Step 3: 实现滚动日志(用户全局规范)**

`backend/app/logging_setup.py`:
```python
"""滚动文件日志:按天 + 单文件 50MB 双触发滚动,保留 7 天,全局单 handler。"""
from __future__ import annotations

import logging
import os
import glob
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
MAX_BYTES = 50 * 1024 * 1024
KEEP_DAYS = 7

_handler: logging.Handler | None = None


class DailySizeRotatingHandler(RotatingFileHandler):
    """按天滚动 + 超过 MAX_BYTES 立即滚动;后缀精确到秒防同日覆盖。"""

    def __init__(self, base_path: str):
        self.base_path = base_path
        stamp = datetime.now().strftime("%Y%m%d")
        super().__init__(f"{base_path}.{stamp}", maxBytes=MAX_BYTES,
                         backupCount=KEEP_DAYS * 50, encoding="utf-8")
        self.day_stamp = stamp

    def emit(self, record: logging.LogRecord) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if today != self.day_stamp:  # 跨天:换新文件并清理过期
            self.day_stamp = today
            self.baseFilename = os.path.abspath(f"{self.base_path}.{today}")
            self.stream = None
            if self.backupCount > 0:
                self._cleanup_expired()
        super().emit(record)

    def _cleanup_expired(self) -> None:
        cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
        for f in glob.glob(f"{self.base_path}.*"):
            stamp = f.rsplit(".", 1)[-1]
            if stamp[:8] < cutoff:
                try:
                    os.remove(f)
                except OSError:
                    pass


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _handler
    logger = logging.getLogger("irs-calc")
    logger.setLevel(level)
    if _handler is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        _handler = DailySizeRotatingHandler(os.path.join(LOG_DIR, "irs-calc.log"))
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(_handler)
        logger.propagate = False
    return logger
```

- [ ] **Step 4: 实现 schemas / services / market / main**

`backend/app/api/schemas.py`:
```python
"""API 请求/响应模型。接口层利率一律用百分数(1.65 = 1.65%),内核层用小数。"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CurvePointIn(BaseModel):
    tenor: str
    rate: float  # %


class MarketOut(BaseModel):
    benchmark: str
    valuation_date: date
    curve: list[CurvePointIn]
    fixing: dict | None = None        # {"date": "2026-11-06", "rate": 1.4}(%)
    calendar_approximate: bool = False


class TradeRequest(BaseModel):
    benchmark: Literal["FR007", "SHIBOR3M"]
    direction: Literal["receiver", "payer"]
    notional: float = Field(gt=0)
    fixed_rate: float                  # %
    spread: float = 0.0                # %
    effective_date: date
    maturity_date: date
    fixed_freq_months: int = Field(default=3, ge=1, le=12)
    valuation_date: date
    curve: list[CurvePointIn] = []     # 空 = 按估值日自动从行情加载
    fixing_overrides: dict[str, float] = {}  # {"2026-11-05": 1.37}(%)


class AttributionRequest(TradeRequest):
    start_date: date                   # t0


class Krdv01Out(BaseModel):
    tenor: str
    dv01: float


class ValueResponse(BaseModel):
    npv: float
    pv_fixed: float
    pv_floating: float
    dv01_parallel: float
    krdv01: list[Krdv01Out]
    cashflows: dict                    # {"fixed": [...], "floating": [...]}
    warnings: list[str]


class AttributionResponse(BaseModel):
    delta_npv: float
    cf: float
    components: dict                   # theta/carry/roll/curve/spread/residual
    identity: dict                     # {"ok": bool, "diff": float}
    detail: list[dict]
    valuation_t1: ValueResponse
    warnings: list[str]
```

`backend/app/api/services.py`:
```python
"""请求 ↔ 内核转换层:单位换算(百分点↔小数)、数据装配、错误映射。"""
from __future__ import annotations

from datetime import date

from app.core import risk
from app.core.attribution import run_attribution
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import value_swap
from app.core.schedule import add_months
from app.dataio import loader
from app.api.schemas import AttributionRequest, TradeRequest


def get_calendar() -> Calendar:
    return loader.build_calendar()


def load_fixings(benchmark: str, overrides: dict[str, float] | None = None) -> dict[date, float]:
    fx = dict(loader.fixings_for(benchmark))
    for d, v in (overrides or {}).items():
        fx[date.fromisoformat(d)] = v / 100.0
    return fx


def build_curve(benchmark: str, valuation_date: date,
                curve_in: list | None) -> ZeroCurve:
    if curve_in:
        pts = [CurvePoint(p.tenor, add_months(valuation_date, _months(p.tenor)), p.rate / 100.0)
               for p in curve_in]
        return ZeroCurve(valuation_date, pts)
    return ZeroCurve(valuation_date, loader.curve_for(benchmark, valuation_date))


def _months(tenor: str) -> int:
    from app.core.conventions import tenor_to_months
    return tenor_to_months(tenor)


def request_to_trade(req: TradeRequest) -> dict:
    return {
        "benchmark": req.benchmark,
        "direction": req.direction,
        "notional": req.notional,
        "fixed_rate": req.fixed_rate / 100.0,
        "spread": req.spread / 100.0,
        "effective_date": req.effective_date,
        "maturity_date": req.maturity_date,
        "fixed_freq_months": req.fixed_freq_months,
    }


def do_value(req: TradeRequest, calendar: Calendar) -> dict:
    spec = BENCHMARKS[req.benchmark]
    trade = request_to_trade(req)
    curve = build_curve(req.benchmark, req.valuation_date, req.curve)
    fixings = load_fixings(req.benchmark, req.fixing_overrides)
    warnings = []
    if not req.curve:
        pass  # 曲线来自行情;坏点不清洗(用户决策),界面可改
    val = value_swap(trade, req.valuation_date, curve, calendar, spec, fixings=fixings)
    dv = risk.parallel_dv01(trade, req.valuation_date, curve, calendar, spec, fixings=fixings)
    keys = risk.key_tenors_for(curve, req.maturity_date)
    parts = risk.krdv01(trade, req.valuation_date, curve, calendar, spec,
                        fixings=fixings, key_tenors=keys)
    return {
        "npv": val["npv"],
        "pv_fixed": val["pv_fixed"],
        "pv_floating": val["pv_floating"],
        "dv01_parallel": dv,
        "krdv01": [{"tenor": x["tenor"], "dv01": x["dv01"]} for x in parts],
        "cashflows": {
            "fixed": _rows(val["fixed_rows"]),
            "floating": _rows(val["floating_rows"]),
        },
        "warnings": warnings,
    }


def _rows(rows):
    return [{
        "pay_date": r.pay_date.isoformat(),
        "accrual_start": r.accrual_start.isoformat(),
        "accrual_end": r.accrual_end.isoformat(),
        "days": r.days,
        "tau": r.tau,
        "rate": r.rate * 100.0,
        "amount": r.amount,
        "df": r.df,
        "pv": r.pv,
        "sub_periods": [{
            "reset_date": sp.reset_date.isoformat(),
            "accrual_start": sp.accrual_start.isoformat(),
            "accrual_end": sp.accrual_end.isoformat(),
            "days": sp.days,
            "tau": sp.tau,
            "rate": sp.rate * 100.0,
            "source": sp.source,
        } for sp in r.sub_periods],
    } for r in rows]


def do_attribution(req: AttributionRequest, calendar: Calendar) -> dict:
    spec = BENCHMARKS[req.benchmark]
    trade = request_to_trade(req)
    curve_t0 = build_curve(req.benchmark, req.start_date, req.curve)
    curve_t1 = build_curve(req.benchmark, req.valuation_date, req.curve)
    fixings = load_fixings(req.benchmark, req.fixing_overrides)
    res = run_attribution(trade=trade, start_date=req.start_date, end_date=req.valuation_date,
                          curve_t0=curve_t0, curve_t1=curve_t1, fixings=fixings,
                          calendar=calendar, spec=spec)
    value_part = do_value(req, calendar)
    return {
        "delta_npv": res.delta_npv,
        "cf": res.cf,
        "components": {"theta": res.theta, "carry": res.carry, "roll": res.roll,
                       "curve": res.curve_effect, "spread": res.spread,
                       "residual": res.residual},
        "identity": {"ok": res.identity_ok, "diff": res.identity_diff},
        "detail": res.detail,
        "valuation_t1": value_part,
        "warnings": res.warnings,
    }
```

注意:`do_attribution` 里 `build_curve(req.benchmark, req.start_date, req.curve)` 复用同一份曲线输入时,期限点日期按各自估值日重算,即"两日同曲线形状"——这正是默认情景;若 t0/t1 需要不同曲线,后续版本再加 `start_curve` 字段(设计 §5.3 的 `start_curve` 为可选扩展,YAGNI 暂不做,详见计划自审说明)。

`backend/app/api/market.py`:
```python
"""GET /api/market:按日预填曲线 + 最新定盘。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import MarketOut
from app.dataio import loader

router = APIRouter(prefix="/api")

BENCH_VALID = {"FR007", "SHIBOR3M"}


@router.get("/market", response_model=MarketOut)
def get_market(benchmark: str = Query(...), date: date = Query(...)):
    if benchmark not in BENCH_VALID:
        raise HTTPException(422, f"不支持的基准: {benchmark}")
    try:
        pts = loader.curve_for(benchmark, date)
    except loader.MarketDataError as e:
        raise HTTPException(404, str(e))
    fx = loader.fixings_for(benchmark)
    fixing = None
    if fx:
        latest = max(d for d in fx if d <= date)
        fixing = {"date": latest.isoformat(), "rate": fx[latest] * 100.0}
    cal = loader.build_calendar()
    return MarketOut(
        benchmark=benchmark, valuation_date=date,
        curve=[{"tenor": p.label, "rate": p.rate * 100.0} for p in pts],
        fixing=fixing, calendar_approximate=cal.uses_fallback(date))
```

`backend/app/main.py`:
```python
"""IRS 计算器 FastAPI 入口。"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.market import router as market_router
from app.logging_setup import setup_logging

setup_logging()
app = FastAPI(title="IRS Calculator", version="0.1.0")
app.include_router(market_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_api.py -v
```
Expected: 4 passed。

- [ ] **Step 6: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(api): /api/market 行情预填接口 + 滚动日志"
```

---

### Task 12: API — 估值与归因接口

**Files:**
- Create: `backend/app/api/valuation.py`
- Create: `backend/app/api/attribution.py`
- Modify: `backend/app/main.py`(注册路由)
- Modify: `backend/tests/test_api.py`(追加测试)

- [ ] **Step 1: 追加失败测试**

`backend/tests/test_api.py` 末尾追加:
```python
VALUE_REQ = {
    "benchmark": "FR007", "direction": "receiver",
    "notional": 100_000_000, "fixed_rate": 1.65, "spread": 0.0,
    "effective_date": "2026-06-01", "maturity_date": "2026-12-01",
    "fixed_freq_months": 3, "valuation_date": "2026-06-01",
    "curve": [
        {"tenor": "6M", "rate": 1.4}, {"tenor": "1Y", "rate": 1.4},
        {"tenor": "2Y", "rate": 1.4}],
    "fixing_overrides": {"2026-06-01": 1.4},
}


def test_value_matches_core():
    from datetime import date as D, timedelta
    from app.core.calendar import Calendar
    from app.core.conventions import BENCHMARKS
    from app.core.curve import CurvePoint, ZeroCurve
    from app.core.pricing import value_swap

    r = client.post("/api/value", json=VALUE_REQ)
    assert r.status_code == 200
    body = r.json()
    # 与内核直接计算严格一致(双重记账校验)
    d = D(2025, 1, 1)
    cal_days = set()
    while d <= D(2026, 12, 31):
        if d.weekday() < 5:
            cal_days.add(d)
        d += timedelta(days=1)
    cal = Calendar(cal_days)
    curve = ZeroCurve(D(2026, 6, 1), [CurvePoint(t, D(2026, 12, 1) if t == "6M"
                                                  else D(2027, 6, 1) if t == "1Y"
                                                  else D(2028, 6, 1), 0.014)
                                      for t in ("6M", "1Y", "2Y")])
    trade = {"benchmark": "FR007", "direction": "receiver", "notional": 1e8,
             "fixed_rate": 0.0165, "spread": 0.0, "effective_date": D(2026, 6, 1),
             "maturity_date": D(2026, 12, 1), "fixed_freq_months": 3}
    expect = value_swap(trade, D(2026, 6, 1), curve, cal, BENCHMARKS["FR007"],
                        fixings={D(2026, 6, 1): 0.014})
    assert body["npv"] == pytest.approx(expect["npv"])
    assert body["pv_fixed"] > body["pv_floating"]
    assert body["cashflows"]["fixed"][0]["rate"] == pytest.approx(1.65)
    assert body["cashflows"]["floating"][0]["sub_periods"][0]["source"] == "fixing"


def test_value_missing_fixing_422():
    bad = {**VALUE_REQ, "fixing_overrides": {}}
    r = client.post("/api/value", json=bad)
    assert r.status_code == 422
    assert "定盘" in r.json()["detail"]


def test_attribution_identity_ok():
    req = {**VALUE_REQ,
           "start_date": "2026-06-01", "valuation_date": "2026-06-08",
           "effective_date": "2026-06-01", "maturity_date": "2028-06-01",
           "fixing_overrides": {"2026-06-01": 1.4}}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["ok"] is True
    assert set(body["components"]) == {"theta", "carry", "roll", "curve", "spread", "residual"}
    assert body["cf"] == pytest.approx(0.0)


def test_attribution_bad_dates_422():
    req = {**VALUE_REQ, "start_date": "2026-06-08", "valuation_date": "2026-06-01"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_api.py -v
```
Expected: FAIL(404 Not Found:路由不存在)。

- [ ] **Step 3: 实现两个路由**

`backend/app/api/valuation.py`:
```python
"""POST /api/value 单日估值。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import TradeRequest, ValueResponse
from app.api.services import do_value, get_calendar
from app.core.pricing import MissingFixingError
from app.dataio.loader import MarketDataError

router = APIRouter(prefix="/api")


@router.post("/value", response_model=ValueResponse)
def post_value(req: TradeRequest):
    if req.effective_date >= req.maturity_date:
        raise HTTPException(400, "起息日必须早于到期日")
    if req.valuation_date > req.maturity_date:
        raise HTTPException(400, "估值日不能晚于到期日")
    calendar = get_calendar()
    try:
        return do_value(req, calendar)
    except MissingFixingError as e:
        raise HTTPException(422, f"缺少定盘利率: {e}。请在 fixing_overrides 中提供。")
    except MarketDataError as e:
        raise HTTPException(404, str(e))
```

`backend/app/api/attribution.py`:
```python
"""POST /api/attribution 区间归因。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import AttributionRequest, AttributionResponse
from app.api.services import do_attribution, get_calendar
from app.core.pricing import MissingFixingError
from app.dataio.loader import MarketDataError

router = APIRouter(prefix="/api")


@router.post("/attribution", response_model=AttributionResponse)
def post_attribution(req: AttributionRequest):
    if req.start_date >= req.valuation_date:
        raise HTTPException(422, "归因起始日 t0 必须早于估值日 t1")
    if req.effective_date >= req.maturity_date:
        raise HTTPException(400, "起息日必须早于到期日")
    calendar = get_calendar()
    try:
        return do_attribution(req, calendar)
    except MissingFixingError as e:
        raise HTTPException(422, f"缺少定盘利率: {e}。请在 fixing_overrides 中提供。")
    except MarketDataError as e:
        raise HTTPException(404, str(e))
```

`backend/app/main.py` 注册路由(import 区追加):
```python
from app.api.valuation import router as value_router
from app.api.attribution import router as attribution_router
app.include_router(value_router)
app.include_router(attribution_router)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests/test_api.py -v
```
Expected: 9 passed(4 旧 + 5 新)。

- [ ] **Step 5: 全量回归**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(api): 估值与归因接口"
```

---

### Task 13: 静态托管与启动验证

**Files:**
- Modify: `backend/app/main.py`(挂 frontend/dist)

- [ ] **Step 1: main.py 追加静态托管**(dist 不存在时不报错)

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
```

- [ ] **Step 2: 启动冒烟**

```bash
cd /d/git/irs-calc/backend && PYTHONIOENCODING=utf-8 py -m uvicorn app.main:app --port 8000 &
sleep 3 && curl -s http://127.0.0.1:8000/api/health && curl -s -X POST http://127.0.0.1:8000/api/value -H "Content-Type: application/json" -d '{"benchmark":"FR007","direction":"receiver","notional":100000000,"fixed_rate":1.65,"effective_date":"2026-06-01","maturity_date":"2026-12-01","valuation_date":"2026-11-06"}' | head -c 300
```
Expected: `{"status":"ok"}`;value 接口返回含 npv 的 JSON(曲线自动从行情加载 2026-11-06)。
验证后停止:`kill %1`。

- [ ] **Step 3: Commit**

```bash
cd /d/git/irs-calc && git add backend && git commit -m "feat(api): 托管前端构建产物"
```

---

### Task 14: 前端脚手架

**Files:**
- Create: `frontend/`(Vite 生成)
- Modify: `frontend/vite.config.js`、`frontend/src/main.js`、`frontend/src/App.vue`

- [ ] **Step 1: 检查 Node 环境**

```bash
node --version && npm --version
```
Expected: Node ≥ 18。若无 Node,停下向用户说明安装 Node.js LTS。

- [ ] **Step 2: 生成 Vite 项目并装依赖**

```bash
cd /d/git/irs-calc && npm create vite@latest frontend -- --template vue
cd frontend && npm install && npm install element-plus axios
```

- [ ] **Step 3: 配置代理与入口**

`frontend/vite.config.js`:
```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
```

`frontend/src/main.js`:
```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'

createApp(App).use(ElementPlus, { locale: zhCn }).mount('#app')
```

`frontend/src/App.vue`:
```vue
<template>
  <Valuation />
</template>

<script setup>
import Valuation from './views/Valuation.vue'
</script>
```

删除模板自带的多余文件引用:确保 `src/views/` 目录存在(`mkdir -p src/views`),`src/components/HelloWorld.vue` 留存不影响。

- [ ] **Step 4: 冒烟 dev server**

先启动后端(另一个终端或后台):
```bash
cd /d/git/irs-calc/backend && PYTHONIOENCODING=utf-8 py -m uvicorn app.main:app --port 8000
```
再:
```bash
cd /d/git/irs-calc/frontend && npm run dev &
sleep 5 && curl -s http://127.0.0.1:5173/api/health
```
Expected: `{"status":"ok"}`(代理生效)。停止 dev server:`kill %1`。

- [ ] **Step 5: Commit**

```bash
cd /d/git/irs-calc && git add frontend && git commit -m "chore(frontend): Vite+Vue3+ElementPlus 脚手架与 API 代理"
```

---

### Task 15: 前端估值页(完整实现)

**Files:**
- Create: `frontend/src/api/client.js`
- Create: `frontend/src/views/Valuation.vue`(整文件替换)

- [ ] **Step 1: API 客户端**

`frontend/src/api/client.js`:
```javascript
import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

export const loadMarket = (benchmark, date) =>
  http.get('/market', { params: { benchmark, date } }).then(r => r.data)

export const postValue = (payload) =>
  http.post('/value', payload).then(r => r.data)

export const postAttribution = (payload) =>
  http.post('/attribution', payload).then(r => r.data)
```

- [ ] **Step 2: 估值页整页实现**

`frontend/src/views/Valuation.vue`:
```vue
<template>
  <el-container style="max-width: 1280px; margin: 0 auto; padding: 16px">
    <el-main>
      <h2>利率互换计算器</h2>

      <!-- ① 合约信息 -->
      <el-card header="① 合约信息" shadow="never" style="margin-bottom: 12px">
        <el-form :model="form" inline label-width="110px">
          <el-form-item label="基准利率">
            <el-select v-model="form.benchmark" style="width: 140px">
              <el-option value="FR007" label="FR007" />
              <el-option value="SHIBOR3M" label="SHIBOR 3M" />
            </el-select>
          </el-form-item>
          <el-form-item label="头寸方向">
            <el-select v-model="form.direction" style="width: 140px">
              <el-option value="receiver" label="收固定" />
              <el-option value="payer" label="付固定" />
            </el-select>
          </el-form-item>
          <el-form-item label="名义本金">
            <el-input-number v-model="form.notional" :min="1" :step="10000000"
                             :controls="false" style="width: 160px" />
          </el-form-item>
          <el-form-item label="固定利率 %">
            <el-input-number v-model="form.fixedRate" :step="0.01" :precision="4"
                             :controls="false" style="width: 120px" />
          </el-form-item>
          <el-form-item label="利差 %">
            <el-input-number v-model="form.spread" :step="0.0001" :precision="4"
                             :controls="false" style="width: 120px" />
          </el-form-item>
          <el-form-item label="起息日">
            <el-date-picker v-model="form.effectiveDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="到期日">
            <el-date-picker v-model="form.maturityDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="固定腿频率">
            <el-select v-model="form.fixedFreqMonths" style="width: 120px">
              <el-option :value="3" label="季度" />
              <el-option :value="12" label="年度" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- ② 市场数据 -->
      <el-card header="② 市场数据" shadow="never" style="margin-bottom: 12px">
        <el-form inline label-width="110px">
          <el-form-item label="估值日 t1">
            <el-date-picker v-model="form.valuationDate" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
          <el-form-item label="归因起始日 t0">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD"
                            placeholder="选填,填了才能算归因" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" plain :loading="loadingMarket" @click="onLoadMarket">
              加载行情
            </el-button>
            <el-button type="primary" :loading="loadingValue" @click="onValue">
              计算估值
            </el-button>
            <el-button type="success" :loading="loadingAttr" :disabled="!form.startDate"
                       @click="onAttribution">
              计算归因
            </el-button>
          </el-form-item>
        </el-form>
        <el-alert v-if="marketApprox" type="warning" :closable="false"
                  title="当前日期在交易日历数据范围之外,日历按周末规则近似" style="margin-bottom: 8px" />
        <el-table :data="curveRows" size="small" style="width: 100%">
          <el-table-column prop="tenor" label="期限" width="90" />
          <el-table-column label="零息利率 %">
            <template #default="{ row }">
              <el-input-number v-model="row.rate" :precision="4" :controls="false"
                               size="small" style="width: 120px" />
            </template>
          </el-table-column>
        </el-table>
        <div v-if="fixingInfo" style="margin-top: 8px; color: #909399; font-size: 13px">
          当期定盘:{{ form.benchmark === 'FR007' ? 'FR007' : 'Shibor 3M' }}
          {{ fixingInfo.date }} = {{ fixingInfo.rate }}%
        </div>
      </el-card>

      <!-- ③ 结果区 -->
      <el-card v-if="warnings.length" shadow="never" style="margin-bottom: 12px">
        <el-alert v-for="(w, i) in warnings" :key="i" :title="w" type="warning"
                  :closable="false" style="margin-bottom: 4px" />
      </el-card>

      <el-card v-if="valueResult" shadow="never" style="margin-bottom: 12px">
        <template #header>③ 估值结果</template>
        <el-row :gutter="12">
          <el-col :span="6"><stat-card title="NPV(元)" :v="valueResult.npv" /></el-col>
          <el-col :span="6"><stat-card title="固定腿 PV(元)" :v="valueResult.pv_fixed" /></el-col>
          <el-col :span="6"><stat-card title="浮动腿 PV(元)" :v="valueResult.pv_floating" /></el-col>
          <el-col :span="6"><stat-card title="平行 DV01(元/bp)" :v="valueResult.dv01_parallel" /></el-col>
        </el-row>
      </el-card>

      <el-tabs v-model="activeTab" style="margin-bottom: 24px">
        <el-tab-pane label="关键期限 DV01" name="krdv">
          <el-table v-if="valueResult" :data="valueResult.krdv01" size="small">
            <el-table-column prop="tenor" label="期限" width="90" />
            <el-table-column prop="dv01" label="KRDV01(元/bp)">
              <template #default="{ row }">{{ fmt(row.dv01) }}</template>
            </el-table-column>
          </el-table>
          <div v-if="valueResult" style="color:#909399;font-size:13px;margin-top:6px">
            合计 = {{ fmt(krdvSum) }};应等于平行 DV01
          </div>
        </el-tab-pane>

        <el-tab-pane label="现金流明细" name="cf">
          <template v-if="valueResult">
            <h4>固定腿</h4>
            <el-table :data="valueResult.cashflows.fixed" size="small" border>
              <el-table-column prop="pay_date" label="支付日" width="110" />
              <el-table-column prop="accrual_start" label="计息起" width="110" />
              <el-table-column prop="accrual_end" label="计息止" width="110" />
              <el-table-column prop="days" label="天数" width="70" />
              <el-table-column prop="rate" label="利率 %">
                <template #default="{ row }">{{ row.rate.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="现金流(元)">
                <template #default="{ row }">{{ fmt(row.amount) }}</template>
              </el-table-column>
              <el-table-column label="DF">
                <template #default="{ row }">{{ row.df.toFixed(6) }}</template>
              </el-table-column>
              <el-table-column label="现值(元)">
                <template #default="{ row }">{{ fmt(row.pv) }}</template>
              </el-table-column>
            </el-table>
            <h4 style="margin-top:16px">浮动腿(展开行查看重置子区间)</h4>
            <el-table :data="valueResult.cashflows.floating" size="small" border row-key="pay_date">
              <el-table-column type="expand">
                <template #default="{ row }">
                  <el-table :data="row.sub_periods" size="small">
                    <el-table-column prop="reset_date" label="重置日" width="110" />
                    <el-table-column prop="accrual_start" label="起" width="110" />
                    <el-table-column prop="accrual_end" label="止" width="110" />
                    <el-table-column prop="days" label="天数" width="70" />
                    <el-table-column label="利率 %">
                      <template #default="{ row: sp }">{{ sp.rate.toFixed(4) }}</template>
                    </el-table-column>
                    <el-table-column prop="source" label="来源" width="90" />
                  </el-table>
                </template>
              </el-table-column>
              <el-table-column prop="pay_date" label="支付日" width="110" />
              <el-table-column prop="days" label="天数" width="70" />
              <el-table-column label="利率 %">
                <template #default="{ row }">{{ row.rate.toFixed(4) }}</template>
              </el-table-column>
              <el-table-column label="现金流(元)">
                <template #default="{ row }">{{ fmt(row.amount) }}</template>
              </el-table-column>
              <el-table-column label="DF">
                <template #default="{ row }">{{ row.df.toFixed(6) }}</template>
              </el-table-column>
              <el-table-column label="现值(元)">
                <template #default="{ row }">{{ fmt(row.pv) }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-tab-pane>

        <el-tab-pane label="Campisi 归因" name="attr" :disabled="!attributionResult">
          <template v-if="attributionResult">
            <el-row :gutter="12" style="margin-bottom: 12px">
              <el-col :span="6"><stat-card title="全价损益 ΔNPV" :v="attributionResult.delta_npv" /></el-col>
              <el-col :span="6"><stat-card title="区间现金流 CF" :v="attributionResult.cf" /></el-col>
              <el-col :span="6">
                <el-card shadow="never">
                  <div style="color:#909399;font-size:13px">勾稽校验</div>
                  <div :style="{ color: attributionResult.identity.ok ? '#67c23a' : '#f56c6c' }">
                    {{ attributionResult.identity.ok ? '通过' : '失败' }}
                    (差 {{ attributionResult.identity.diff.toExponential(2) }})
                  </div>
                </el-card>
              </el-col>
            </el-row>
            <el-table :data="attrRows" size="small" border>
              <el-table-column prop="label" label="分项" width="220" />
              <el-table-column label="金额(元)" align="right">
                <template #default="{ row }">{{ fmt(row.value) }}</template>
              </el-table-column>
              <el-table-column label="含义" />
            </el-table>
            <h4 style="margin-top:16px">曲线效应明细</h4>
            <el-table :data="attributionResult.detail" size="small" border>
              <el-table-column prop="tenor" label="期限" width="90" />
              <el-table-column label="Δy(bp)" align="right">
                <template #default="{ row }">{{ row.dy_bp.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="KRDV01(元/bp)" align="right">
                <template #default="{ row }">{{ fmt(row.krdv01) }}</template>
              </el-table-column>
              <el-table-column label="贡献(元)" align="right">
                <template #default="{ row }">{{ fmt(row.contribution) }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, defineComponent, h, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { loadMarket, postAttribution, postValue } from '../api/client'

const StatCard = defineComponent({
  props: { title: String, v: Number },
  setup(props) {
    return () => h('el-card', { shadow: 'never' }, () => [
      h('div', { style: 'color:#909399;font-size:13px' }, props.title),
      h('div', {
        style: `font-size:20px;font-weight:600;color:${props.v < 0 ? '#f56c6c' : '#303133'}`,
      }, formatNumber(props.v)),
    ])
  },
})

function formatNumber(v) {
  if (v == null || Number.isNaN(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const form = ref({
  benchmark: 'FR007', direction: 'receiver', notional: 100000000,
  fixedRate: 1.65, spread: 0.0,
  effectiveDate: '2026-06-01', maturityDate: '2026-12-01',
  fixedFreqMonths: 3, valuationDate: '2026-11-06', startDate: '',
})
const curveRows = ref([])
const fixingInfo = ref(null)
const marketApprox = ref(false)
const loadingMarket = ref(false)
const loadingValue = ref(false)
const loadingAttr = ref(false)
const valueResult = ref(null)
const attributionResult = ref(null)
const warnings = ref([])
const activeTab = ref('krdv')

const fmt = formatNumber
const krdvSum = computed(() =>
  valueResult.value ? valueResult.value.krdv01.reduce((s, x) => s + x.dv01, 0) : 0)

const attrRows = computed(() => {
  const a = attributionResult.value
  if (!a) return []
  const c = a.components
  return [
    { label: '时间效应 Θ(其中:)', value: c.theta },
    { label: '  票息效应 Carry', value: c.carry },
    { label: '  骑乘效应 Roll-down', value: c.roll },
    { label: '曲线效应 Curve', value: c.curve },
    { label: '利差效应 Spread', value: c.spread },
    { label: '残差 ε', value: c.residual },
  ]
})

function payload() {
  return {
    benchmark: form.value.benchmark,
    direction: form.value.direction,
    notional: form.value.notional,
    fixed_rate: form.value.fixedRate,
    spread: form.value.spread,
    effective_date: form.value.effectiveDate,
    maturity_date: form.value.maturityDate,
    fixed_freq_months: form.value.fixedFreqMonths,
    valuation_date: form.value.valuationDate,
    curve: curveRows.value.map(r => ({ tenor: r.tenor, rate: r.rate })),
    fixing_overrides: {},
  }
}

function errText(e) {
  const d = e?.response?.data?.detail
  return typeof d === 'string' ? d : '请求失败'
}

async function onLoadMarket() {
  loadingMarket.value = true
  try {
    const m = await loadMarket(form.value.benchmark, form.value.valuationDate)
    curveRows.value = m.curve.map(x => ({ ...x }))
    fixingInfo.value = m.fixing
    marketApprox.value = m.calendar_approximate
    valueResult.value = null
    attributionResult.value = null
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingMarket.value = false
  }
}

async function onValue() {
  loadingValue.value = true
  try {
    valueResult.value = await postValue(payload())
    warnings.value = valueResult.value.warnings || []
    attributionResult.value = null
    activeTab.value = 'krdv'
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingValue.value = false
  }
}

async function onAttribution() {
  loadingAttr.value = true
  try {
    const p = { ...payload(), start_date: form.value.startDate }
    attributionResult.value = await postAttribution(p)
    warnings.value = attributionResult.value.warnings || []
    activeTab.value = 'attr'
  } catch (e) {
    ElMessage.error(errText(e))
  } finally {
    loadingAttr.value = false
  }
}
</script>
```

- [ ] **Step 3: 联调验证(后端 8000 + 前端 5173 同时运行)**

浏览器打开 `http://127.0.0.1:5173`,手动核对:
1. 默认 FR007、t1=2026-11-06,点"加载行情" → 曲线 11 行 1M=1.3838…,定盘 1.4%
2. 点"计算估值" → NPV 卡片出数;DV01 页签合计≈平行 DV01
3. 填 t0=2026-11-05,点"计算归因" → 勾稽校验"通过",各分项出数
4. 现金流页签浮动腿展开可见重置子区间,source 为 fixing/forward

- [ ] **Step 4: Commit**

```bash
cd /d/git/irs-calc && git add frontend && git commit -m "feat(frontend): 估值页(合约表单/曲线编辑/估值/归因/现金流)"
```

---

### Task 16: 端到端验收(生产构建)

- [ ] **Step 1: 前端生产构建**

```bash
cd /d/git/irs-calc/frontend && npm run build
```
Expected: 生成 `dist/`,无报错。

- [ ] **Step 2: 单服务验收**

```bash
cd /d/git/irs-calc/backend && PYTHONIOENCODING=utf-8 py -m uvicorn app.main:app --port 8000 &
sleep 3 && curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/
```
Expected: `200`(FastAPI 托管前端)。浏览器打开 `http://127.0.0.1:8000` 重复 Task 15 Step 3 的四项核对。

- [ ] **Step 3: 全量测试最后确认**

```bash
cd /d/git/irs-calc/backend && py -m pytest tests -v
```
Expected: 全部通过。

- [ ] **Step 4: Commit(验收记录)**

```bash
cd /d/git/irs-calc && git add -A && git commit -m "chore: 端到端验收通过" --allow-empty
```

---

## 计划自审记录

1. **Spec 覆盖**:设计 §4 口径 → Task 1-8、10;§3 数据加载 → Task 9;§5 API → Task 11-12;§6 界面 → Task 14-15;§7 错误处理与日志 → Task 11-12;§8 测试 → 各 Task 内嵌 + 真实数据快照(Task 9);§4.6 日历 → Task 2 + 9。
2. **设计 §5.3 的 `start_curve` 字段**:一期 YAGNI 不做——t0/t1 曲线各自按日期从行情自动加载;若用户显式给 curve,两日同形。已在 Task 11 services 注释说明。
3. **类型一致性**:`price_floating_leg`/`value_swap`/`krdv01` 在 Task 10 的扩展签名已回写 Task 8 调用处兼容(新增参数均带默认值);`AttributionResult.detail` 字段名 `{tenor, dy_bp, krdv01, contribution}` 与前端 Task 15 表格列一致。
4. **已知取舍**:平缓曲线下"远期=平价利率"是近似(单利贴现结构性偏差 ~0.05bp),测试全部改用精确表达式,不引入虚假直觉。

