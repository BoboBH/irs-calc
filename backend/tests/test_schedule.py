from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.schedule import (
    add_months,
    add_tenor,
    build_fixed_skeleton,
    build_floating_skeleton,
)

# 2026-05-25 ~ 2026-12-31 中所有工作日视为交易日(测试用简化日历)
BD = set()
d = date(2026, 5, 25)
while d <= date(2026, 12, 31):
    if d.weekday() < 5:
        BD.add(d)
    d = d.fromordinal(d.toordinal() + 1)
CAL = Calendar(BD)


def test_fixed_skeleton_two_quarters():
    sk = build_fixed_skeleton(date(2026, 6, 1), date(2026, 12, 1), 3, CAL)
    assert len(sk.periods) == 2
    p1, p2 = sk.periods
    assert (p1.accrual_start, p1.accrual_end, p1.pay_date) == (
        date(2026, 6, 1), date(2026, 9, 1), date(2026, 9, 1))
    assert (p2.accrual_start, p2.accrual_end, p2.pay_date) == (
        date(2026, 9, 1), date(2026, 12, 1), date(2026, 12, 1))


def test_fixed_skeleton_annual_freq():
    sk = build_fixed_skeleton(date(2026, 6, 1), date(2028, 6, 1), 12, CAL)
    assert len(sk.periods) == 2
    assert sk.periods[0].accrual_end == date(2027, 6, 1)


def test_fixed_skeleton_adjusted_payment():
    # 2026-09-05 是周六 → 付息日顺延到 09-07(周一),未跨月
    sk = build_fixed_skeleton(date(2026, 6, 5), date(2026, 12, 5), 3, CAL)
    assert sk.periods[0].pay_date == date(2026, 9, 7)


def test_fr007_sub_periods_weekly():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(date(2026, 6, 1), date(2026, 12, 1), CAL, spec)
    p1 = sk.periods[0]
    # 06-01 → 09-01 = 92 天 = 13 个整周(91 天) + 1 天末段
    assert len(p1.sub_periods) == 14
    assert p1.sub_periods[0].reset_date == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_start == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_end == date(2026, 6, 8)
    assert p1.sub_periods[1].reset_date == date(2026, 6, 8)
    assert p1.sub_periods[-1].accrual_end == date(2026, 9, 1)
    # 子区间天数之和 = 期间天数
    total = sum((sp.accrual_end - sp.accrual_start).days for sp in p1.sub_periods)
    assert total == 92
    # 子区间首尾相接
    for a, b in zip(p1.sub_periods, p1.sub_periods[1:]):
        assert a.accrual_end == b.accrual_start


def test_shibor3m_single_sub_period():
    spec = BENCHMARKS["SHIBOR3M"]
    sk = build_floating_skeleton(date(2026, 6, 1), date(2026, 12, 1), CAL, spec)
    p1 = sk.periods[0]
    assert len(p1.sub_periods) == 1
    assert p1.sub_periods[0].reset_date == p1.accrual_start == date(2026, 6, 1)
    assert p1.sub_periods[0].accrual_end == p1.accrual_end == date(2026, 9, 1)


def test_period_dates_adjusted():
    spec = BENCHMARKS["FR007"]
    sk = build_floating_skeleton(date(2026, 6, 5), date(2026, 12, 5), CAL, spec)
    p1 = sk.periods[0]
    # 起息日 06-05(周五)调整后仍为自身;期末 09-05(周六)→ 09-07
    assert p1.accrual_start == date(2026, 6, 5)
    assert p1.pay_date == date(2026, 9, 7)
    assert p1.sub_periods[0].reset_date == date(2026, 6, 5)
    assert p1.sub_periods[-1].accrual_end == date(2026, 9, 7)


def test_add_months_clamps_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_schedule_skips_zero_length_period_after_adjustment():
    """月末钳制把中间期压到与到期重合时,跳过 0 天期。

    effective=2026-05-30(周六,修正顺延回 05-29)、maturity=2026-08-31、月频:
    网格 05-30/06-30/07-30/08-30,而 08-30 调整后 = 08-31 与到期重合,原实现会
    再补一行 (08-31, 08-31) 0 天期;修后跳过该期,到期期 (07-30, 08-31) 完整。
    两腿共用的 _build_periods 同修:浮动腿季付同样不再出现 0 天尾期。"""
    sk = build_fixed_skeleton(date(2026, 5, 30), date(2026, 8, 31), 1, CAL)
    assert all(p.accrual_start < p.accrual_end for p in sk.periods)
    assert sk.periods[-1].accrual_end == date(2026, 8, 31)
    assert len(sk.periods) == 3
    skf = build_floating_skeleton(date(2026, 5, 30), date(2026, 8, 31), CAL, BENCHMARKS["FR007"])
    assert all(p.accrual_start < p.accrual_end for p in skf.periods)
    assert skf.periods[-1].accrual_end == date(2026, 8, 31)


def test_add_tenor_day_label():
    """'7D' 按日历日推进(厂商曲线短端锚点用)。"""
    assert add_tenor(date(2026, 11, 5), "7D") == date(2026, 11, 12)


def test_add_tenor_month_and_year_labels():
    assert add_tenor(date(2026, 11, 5), "1M") == date(2026, 12, 5)
    assert add_tenor(date(2026, 11, 5), "3M") == date(2027, 2, 5)
    assert add_tenor(date(2026, 11, 5), "10Y") == date(2036, 11, 5)
