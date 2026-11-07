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
