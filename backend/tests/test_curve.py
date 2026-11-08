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


def test_df_before_valuation_back_extrapolates():
    """锚定日之前 DF 按同式反推(τ<0 → DF>1);静态归因曲线需要它。"""
    c = make_flat_curve(0.014)
    d = date(2026, 5, 25)  # VAL − 7 天
    tau = (d - VAL).days / 365
    expected = 1.0 / (1.0 + 0.014 * tau)
    assert c.df(d) == expected
    assert c.df(d) > 1.0


def test_forward_straddling_valuation_flat_curve():
    """跨锚定日的远期不受钳制影响:平缓曲线 F = y/(1+y·τ(d1)),d1 可早于锚定日。"""
    c = make_flat_curve(0.014)
    f = c.forward(date(2026, 5, 25), date(2026, 6, 1))
    expected = 0.014 / (1 + 0.014 * (-7 / 365))
    # 7 天 τ 的 (DF−1) 有灾难性抵消,ULP 噪声 ~1e-14,取 1e-12(仍远紧于 2e-3 级缺陷)
    assert abs(f - expected) < 1e-12


def test_df_cont_basis_formula():
    """cont 口径:DF = exp(−y·τ)(连续复利,与外部厂商系统对账用)。"""
    import math
    d = date(2026, 9, 1)
    c = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                        CurvePoint("1Y", date(2027, 6, 1), 0.014),
                        CurvePoint("2Y", date(2028, 6, 1), 0.014)], "cont")
    assert c.df(d) == math.exp(-0.014 * 92 / 365)


def test_df_cont_less_than_simple_for_positive_rate():
    simple = make_flat_curve(0.014)
    cont = ZeroCurve(VAL, simple.points, "cont")
    d = date(2028, 6, 1)
    assert cont.df(d) < simple.df(d)


def test_shifted_curves_preserve_discount_basis():
    cont = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                           CurvePoint("1Y", date(2027, 6, 1), 0.014),
                           CurvePoint("2Y", date(2028, 6, 1), 0.014)], "cont")
    assert cont.shifted_parallel(1e-4).discount_basis == "cont"
    keys = [p.date for p in cont.points]
    assert cont.shifted_keys(keys, [0.0, 1e-4, 0.0]).discount_basis == "cont"


def test_constructor_rejects_unknown_discount_basis():
    import pytest
    with pytest.raises(ValueError):
        ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014)], "compound")


# ---- 插值方法(interp)----


def _up_curve(basis="cont", interp="hermite"):
    """单调上行、段距不等:节点之间可区分线性/Hermite。"""
    return ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                           CurvePoint("1Y", date(2027, 6, 1), 0.020),
                           CurvePoint("2Y", date(2028, 6, 1), 0.025)],
                     basis, interp)


def test_hermite_matches_quotes_at_nodes():
    c = _up_curve()
    for p in c.points:
        assert c.zero_rate(p.date) == p.rate


def test_hermite_flat_extrapolation():
    c = _up_curve()
    assert c.zero_rate(date(2028, 9, 1)) == 0.025   # 超末端平推
    assert c.zero_rate(date(2026, 7, 1)) == 0.014   # 超首端平推


def test_hermite_monotone_no_overshoot():
    """单调数据 + Fritsch–Carlson 切线 ⇒ 曲线单调且不越过任一邻点值(无过冲)。"""
    c = _up_curve()
    d, prev = date(2026, 12, 1), 0.013  # 从低于首点起
    while d <= date(2028, 6, 1):
        y = c.zero_rate(d)
        assert 0.014 <= y <= 0.025
        assert y >= prev
        prev = y
        d += __import__("datetime").timedelta(days=7)


def test_hermite_v_shape_stays_within_segment_range():
    """局部极值点切线取 0:V 形曲线两段内部均不越过端点值。"""
    c = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.020),
                        CurvePoint("1Y", date(2027, 6, 1), 0.014),
                        CurvePoint("2Y", date(2028, 6, 1), 0.018)], "cont", "hermite")
    d = date(2026, 12, 1)
    while d <= date(2028, 6, 1):
        assert 0.014 <= c.zero_rate(d) <= 0.020
        d += __import__("datetime").timedelta(days=7)


def test_hermite_differs_from_linear_inside_segment():
    c_lin = _up_curve(interp="linear")
    c_h = _up_curve(interp="hermite")
    d = date(2027, 1, 15)  # 首段约 1/4 处:端点切线 0 ⇒ 与线性严格不同
    assert c_h.zero_rate(d) != c_lin.zero_rate(d)
    # 节点处两种插值一致
    assert c_h.zero_rate(date(2027, 6, 1)) == c_lin.zero_rate(date(2027, 6, 1))


def test_hermite_flat_curve_matches_linear():
    """平缓曲线割率全 0 ⇒ 切线全 0 ⇒ Hermite 退化为线性,远期闭式不变。"""
    c = ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014),
                        CurvePoint("1Y", date(2027, 6, 1), 0.014)], "simple", "hermite")
    assert c.zero_rate(date(2026, 9, 1)) == 0.014
    f = c.forward(date(2026, 9, 1), date(2026, 12, 1), 365)
    expected = 0.014 / (1 + 0.014 * 92 / 365)
    assert abs(f - expected) < 1e-15


def test_hermite_forward_differs_from_linear_forward():
    """浮动端重置利率来自曲线远期(df 比值):非平曲线上两种插值给出不同远期。"""
    c_lin = _up_curve(interp="linear")
    c_h = _up_curve(interp="hermite")
    # 落在 6M–1Y 节点之间的插值段内(平推区两法一致,须避开)
    assert c_lin.forward(date(2027, 1, 15), date(2027, 3, 1)) != \
        c_h.forward(date(2027, 1, 15), date(2027, 3, 1))


def test_shifted_curves_preserve_interp():
    c = _up_curve()
    assert c.shifted_parallel(1e-4).interp == "hermite"
    keys = [p.date for p in c.points]
    assert c.shifted_keys(keys, [1e-4, 0.0, 0.0]).interp == "hermite"


def test_constructor_rejects_unknown_interp():
    import pytest
    with pytest.raises(ValueError):
        ZeroCurve(VAL, [CurvePoint("6M", date(2026, 12, 1), 0.014)], "simple", "cubic")
