"""排期骨架:只生成日期,不含利率。

固定腿:按日历月推进期末日(末端强制为到期日),计息边界与支付日做修正顺延。
浮动腿(FR007):季度期内自调整后起息日每 7 个日历日一个重置子区间,末段截断;
浮动腿(SHIBOR3M):每季度一个子区间,重置日 = 计息期起始日。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.calendar import Calendar
from app.core.conventions import BenchmarkSpec


@dataclass(frozen=True)
class SubPeriodSkeleton:
    reset_date: date
    accrual_start: date
    accrual_end: date


@dataclass(frozen=True)
class PeriodSkeleton:
    accrual_start: date
    accrual_end: date
    pay_date: date
    sub_periods: tuple[SubPeriodSkeleton, ...]


@dataclass(frozen=True)
class ScheduleSkeleton:
    periods: list[PeriodSkeleton]


def add_months(d: date, months: int) -> date:
    """日历月推进,月末日期钳制(如 11-30 +3M = 次年 02-28)。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def _build_periods(effective: date, maturity: date, freq_months: int,
                   calendar: Calendar) -> list[tuple[date, date, date]]:
    """返回 [(调整后 accrual_start, 调整后 accrual_end, 调整后 pay_date)]。"""
    if effective >= maturity:
        raise ValueError("起息日必须早于到期日")
    start_adj = calendar.adjust_modified_following(effective)
    periods = []
    k = freq_months
    while True:
        raw_end = maturity if add_months(effective, k) >= maturity else add_months(effective, k)
        end_adj = calendar.adjust_modified_following(raw_end)
        # 月末钳制可能把中间期(或到期网格日)调整后压到与上一期止点重合:
        # 跳过该零长期(不能 break——到期的完整期次仍要保留),其他期次不变
        if end_adj > start_adj:
            periods.append((start_adj, end_adj, end_adj))
        if raw_end == maturity:
            break
        start_adj = end_adj
        k += freq_months
    return periods


def build_fixed_skeleton(effective: date, maturity: date, freq_months: int,
                         calendar: Calendar) -> ScheduleSkeleton:
    periods = []
    for s, e, pay in _build_periods(effective, maturity, freq_months, calendar):
        periods.append(PeriodSkeleton(s, e, pay, sub_periods=()))
    return ScheduleSkeleton(periods)


def build_floating_skeleton(effective: date, maturity: date, calendar: Calendar,
                            spec: BenchmarkSpec) -> ScheduleSkeleton:
    periods = []
    for s, e, pay in _build_periods(effective, maturity, spec.float_pay_months, calendar):
        subs = []
        if spec.reset_days is None:  # SHIBOR3M:整段一个子区间
            subs.append(SubPeriodSkeleton(s, s, e))
        else:  # FR007:每 7 个日历日一个子区间,边界不调整,末段截断
            cur = s
            while cur < e:
                nxt = min(cur + timedelta(days=spec.reset_days), e)
                subs.append(SubPeriodSkeleton(cur, cur, nxt))
                cur = nxt
        periods.append(PeriodSkeleton(s, e, pay, sub_periods=tuple(subs)))
    return ScheduleSkeleton(periods)
