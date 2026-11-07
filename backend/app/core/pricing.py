"""双腿定价。估值口径 ex-coupon:只含支付日在估值日之后的现金流。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec, year_fraction
from app.core.curve import ZeroCurve
from app.core.schedule import PeriodSkeleton, ScheduleSkeleton, SubPeriodSkeleton


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
    return LegResult(rows=rows, pv=sum((r.pv for r in rows), 0.0))


def _lookup_fixing(fixings: dict[date, float], reset_date: date) -> float:
    """取 reset_date 当日或之前最近一条定盘;缺失抛 MissingFixingError。

    有意不设时效上界(设计 §10 口径:定盘按"重置日当日或之前最近"取);
    定盘新鲜度检查与告警由上层(loader / API)负责。
    """
    candidates = [d for d in fixings if d <= reset_date]
    if not candidates:
        raise MissingFixingError(f"缺少重置日 {reset_date} 及之前的定盘利率")
    return fixings[max(candidates)]


def resolve_sub_rate(sp: SubPeriodSkeleton, valuation: date, curve: ZeroCurve,
                     spec: BenchmarkSpec,
                     fixings: dict[date, float]) -> tuple[float, str]:
    """子区间利率:重置日 ≤ 估值日 → 定盘;否则曲线隐含远期。"""
    if sp.reset_date <= valuation:
        return _lookup_fixing(fixings, sp.reset_date), "fixing"
    return curve.forward(sp.accrual_start, sp.accrual_end, spec.day_count), "forward"


def price_floating_leg(sk: ScheduleSkeleton, notional: float, valuation: date,
                       curve: ZeroCurve, spec: BenchmarkSpec,
                       fixings: dict[date, float], spread: float = 0.0) -> LegResult:
    """浮动腿定价:每期 CF = N·(Σ rₖ·τₖ + spread·Στₖ),τₖ 按基准计息惯例;ex-coupon。

    CashflowRow.rate 为指标利率的 τ 加权均值,**不含 spread**(amount 含 spread,
    勿用 rate·τ 重建金额);sub_periods 保留逐子区间明细。
    """
    if curve.valuation_date != valuation:
        raise ValueError(f"曲线估值日 {curve.valuation_date} 与定价估值日 {valuation} 不一致")
    dc = spec.day_count
    rows: list[CashflowRow] = []
    for p in _eligible_periods(sk, valuation):
        sub_rows: list[SubPeriodRow] = []
        acc = 0.0
        total_tau = 0.0
        for sp in p.sub_periods:
            rate, source = resolve_sub_rate(sp, valuation, curve, spec, fixings)
            tau = year_fraction(sp.accrual_start, sp.accrual_end, dc)
            acc += rate * tau
            total_tau += tau
            sub_rows.append(SubPeriodRow(
                reset_date=sp.reset_date, accrual_start=sp.accrual_start,
                accrual_end=sp.accrual_end, days=(sp.accrual_end - sp.accrual_start).days,
                tau=tau, rate=rate, source=source))
        amount = notional * (acc + spread * total_tau)
        df = curve.df(p.pay_date)
        rows.append(CashflowRow(
            pay_date=p.pay_date, accrual_start=p.accrual_start, accrual_end=p.accrual_end,
            days=(p.accrual_end - p.accrual_start).days, tau=total_tau,
            rate=acc / total_tau if total_tau else 0.0,
            amount=amount, df=df, pv=amount * df, sub_periods=sub_rows))
    return LegResult(rows=rows, pv=sum((r.pv for r in rows), 0.0))
