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
                    spec: BenchmarkSpec, fixings: dict[date, float],
                    fixing_cutoff: date | None = None) -> float:
    return value_swap(trade, valuation, curve, calendar, spec, fixings=fixings,
                      fixing_cutoff=fixing_cutoff)["npv"]


def parallel_dv01(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
                  spec: BenchmarkSpec, *, fixings: dict[date, float],
                  fixing_cutoff: date | None = None) -> float:
    bumped = curve.shifted_parallel(BUMP)
    return _npv_with_curve(trade, valuation, bumped, calendar, spec, fixings,
                           fixing_cutoff) \
        - _npv_with_curve(trade, valuation, curve, calendar, spec, fixings,
                          fixing_cutoff)


def krdv01(trade: dict, valuation: date, curve: ZeroCurve, calendar: Calendar,
           spec: BenchmarkSpec, *, fixings: dict[date, float],
           key_tenors: list[tuple[str, date]],
           fixing_cutoff: date | None = None) -> list[dict]:
    base = _npv_with_curve(trade, valuation, curve, calendar, spec, fixings,
                           fixing_cutoff)
    key_dates = [d for _, d in key_tenors]
    out = []
    for i, (label, kd) in enumerate(key_tenors):
        bumps = [0.0] * len(key_dates)
        bumps[i] = BUMP
        bumped = curve.shifted_keys(key_dates, bumps)
        npv_b = _npv_with_curve(trade, valuation, bumped, calendar, spec, fixings,
                                fixing_cutoff)
        out.append({"tenor": label, "date": kd, "dv01": npv_b - base})
    return out
