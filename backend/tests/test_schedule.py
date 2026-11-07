from datetime import date
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS
from app.core.schedule import build_fixed_skeleton, build_floating_skeleton

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
