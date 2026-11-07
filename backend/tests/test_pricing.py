from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS, year_fraction
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import MissingFixingError, price_fixed_leg, price_floating_leg
from app.core.schedule import build_fixed_skeleton, build_floating_skeleton

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


def test_fixed_leg_pay_on_valuation_excluded():
    """ex-coupon 严格边界:支付日 = 估值日的现金流被剔除(该笔进归因 CF 项)。"""
    sk = build_fixed_skeleton(VAL, date(2026, 12, 1), 3, CAL)
    v = date(2026, 9, 1)
    curve_v = ZeroCurve(v, [CurvePoint("6M", date(2027, 3, 1), 0.014),
                            CurvePoint("1Y", date(2027, 9, 1), 0.014),
                            CurvePoint("2Y", date(2028, 9, 1), 0.014)])
    leg = price_fixed_leg(sk, 100_000_000, 0.0165, v, curve_v, CAL, 365)
    assert [r.pay_date for r in leg.rows] == [date(2026, 12, 1)]
