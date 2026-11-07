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
