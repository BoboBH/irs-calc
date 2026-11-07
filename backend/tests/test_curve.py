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
