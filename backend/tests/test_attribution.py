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
