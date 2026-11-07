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
    return LegResult(rows=rows, pv=sum(r.pv for r in rows))
