import datetime
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
    d += datetime.timedelta(days=1)
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
    """白皮书性质(一阶):关键期限三角形权重扰动下 Σ KRDV01ₖ ≈ 平行 DV01。

    有限差分重估含 O(bump²) 交叉凸性项(1bp 下相对残差 ~8.4e-5),
    故用相对容差;结构性错误(漏期限/权重不归一)会产生 ≥1e-3 级相对差。
    """
    spec = BENCHMARKS["FR007"]
    curve = curve_two_year()
    keys = key_tenors_for(curve, TRADE["maturity_date"])
    parts = krdv01(TRADE, VAL, curve, CAL, spec, fixings=FIXINGS, key_tenors=keys)
    total = sum(x["dv01"] for x in parts)
    dv = parallel_dv01(TRADE, VAL, curve, CAL, spec, fixings=FIXINGS)
    assert abs(total - dv) < 5e-4 * abs(dv)


def test_key_tenors_filtered_by_maturity():
    """2Y 互换只保留日期 ≤ 到期日的期限点。"""
    keys = key_tenors_for(curve_two_year(), date(2026, 12, 1))
    assert [d for _, d in keys] == [date(2026, 7, 1), date(2026, 9, 1), date(2026, 12, 1)]
    assert [t for t, _ in keys] == ["1M", "3M", "6M"]
