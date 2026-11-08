"""Campisi 日频归因(白皮书 §Campisi 归因框架,公式逐条落地)。

分解路径:先时间(静态曲线推进至 t1)、后曲线(在 (t1; C̃_t1) 处一阶展开)。
恒等式:ΔNPV = Θ + Curve + Spread + ε,Spread 恒为 0(单曲线)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec, year_fraction
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import _lookup_fixing, value_swap
from app.core.risk import krdv01, key_tenors_for, parallel_dv01
from app.core.schedule import add_tenor, build_floating_skeleton


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
    identity_ok: bool = False     # = 浮点恒等 + ΣKRDV01 机制校验 + 残差量级门(三者皆可失败)
    identity_diff: float = 0.0    # 恒等式重加总的浮点噪声口径(构造上恒≈0,单独无信息量)
    warnings: list[str] = field(default_factory=list)


def static_curve(curve_t0: ZeroCurve, valuation_t1: date) -> ZeroCurve:
    """静态曲线 C̃_t1:各期限零息利率与 t0 相同,估值日推进至 t1,贴现口径继承。

    期限点日期按 label 重塑('7D' 按日历日、'1M'/'10Y' 按日历月;
    label 为锚,constant maturity 口径)。
    """
    pts = [CurvePoint(p.label, add_tenor(valuation_t1, p.label), p.rate)
           for p in curve_t0.points]
    return ZeroCurve(valuation_t1, pts, curve_t0.discount_basis)


def _zero_at(curve: ZeroCurve, label: str) -> float:
    """曲线在其 label 期限上的零息利率(constant maturity 口径)。"""
    return curve.zero_rate(add_tenor(curve.valuation_date, label))


def _current_reset_fixing(trade: dict, calendar: Calendar, spec: BenchmarkSpec,
                          fixings: dict[date, float], t0: date) -> float:
    """L0:t0 所在重置子区间定盘观察日的已定盘利率(白皮书 §票息效应;
    fixing_lag_bd 与定价侧一致前推)。"""
    lag_bd = int(trade.get("fixing_lag_bd", 0) or 0)
    sk = build_floating_skeleton(trade["effective_date"], trade["maturity_date"],
                                 calendar, spec)
    for p in sk.periods:
        for sp in p.sub_periods:
            if sp.accrual_start <= t0 < sp.accrual_end:
                reset = sp.reset_date
                for _ in range(lag_bd):
                    reset = calendar.prev_business_day(reset)
                return _lookup_fixing(fixings, reset)
    reset = t0
    for _ in range(lag_bd):
        reset = calendar.prev_business_day(reset)
    return _lookup_fixing(fixings, reset)


def run_attribution(*, trade: dict, start_date: date, end_date: date,
                    curve_t0: ZeroCurve, curve_t1: ZeroCurve,
                    fixings: dict[date, float], calendar: Calendar,
                    spec: BenchmarkSpec) -> AttributionResult:
    if start_date >= end_date:
        raise ValueError(f"归因窗口非法: start {start_date} >= end {end_date}")
    eff = trade["effective_date"]
    mat = trade["maturity_date"]
    if end_date <= eff or start_date >= mat:
        raise ValueError(f"归因窗口 [{start_date}, {end_date}] 与合约存续期 ({eff}, {mat}] 无交集")
    N = trade["notional"]
    s = trade.get("spread", 0.0)

    # 1. 全价重估(omega 取自 value_swap,方向规则单点维护)
    res0 = value_swap(trade, start_date, curve_t0, calendar, spec, fixings=fixings)
    omega = res0["omega"]
    npv_t0 = res0["npv"]
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

    # 7. 残差与勾稽(identity_diff 仅为浮点噪声口径;可失败的子校验见下)
    spread = 0.0
    residual = delta_npv - theta - curve_effect - spread
    total = theta + curve_effect + spread + residual
    identity_diff = abs(total - delta_npv)
    warnings = []
    if not keys:
        warnings.append("关键期限集合为空:剩余期限不足最小期限点,曲线效应为 0")
    if keys and trade["maturity_date"] > keys[-1][1]:
        warnings.append(f"到期日晚于最后关键期限点 {keys[-1][0]},"
                        f"尾部敏感度折入该档(末档实为'{keys[-1][0]} 及以后')")
    # 可失败的勾稽子校验:机制校验(ΣKRDV01 ≈ 平行 DV01,一阶性质)+ 残差量级门(ε 为二阶小量)
    para = parallel_dv01(trade, end_date, st, calendar, spec,
                         fixings=fixings, fixing_cutoff=start_date)
    sum_kr = sum(x["dv01"] for x in parts)
    mechanism_ok = abs(sum_kr - para) <= 1e-3 * max(abs(para), 1.0)
    residual_ok = abs(residual) <= 0.05 * max(abs(delta_npv), abs(curve_effect), 1.0)
    identity_ok = identity_diff < 1e-6 and mechanism_ok and residual_ok
    if not mechanism_ok:
        warnings.append("ΣKRDV01 与平行 DV01 相对偏差超 1e-3,曲线扰动机制可能接线错误")
    if not residual_ok:
        warnings.append("残差 ε 量级异常(超过 ΔNPV/Curve 的 5%),分解可能失真")

    return AttributionResult(
        delta_npv=delta_npv, cf=cf, npv_t0=npv_t0, npv_t1=npv_t1,
        npv_static=npv_static, theta=theta, carry=carry, roll=roll,
        curve_effect=curve_effect, spread=spread, residual=residual,
        detail=detail, identity_ok=identity_ok,
        identity_diff=identity_diff, warnings=warnings)
