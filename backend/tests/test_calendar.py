from datetime import date
from app.core.calendar import Calendar

# 用一小段手工构造的交易日:2026-05-25(一)~ 05-29(五)、06-01(一)~ 06-05(五)为交易日(周末非交易日)
BD = {date(2026, 5, d) for d in range(25, 30)} | {date(2026, 6, d) for d in range(1, 6)}


def test_in_range_business_day():
    cal = Calendar(BD)
    assert cal.is_business_day(date(2026, 5, 25))      # 周一,在数据范围内且为交易日
    assert not cal.is_business_day(date(2026, 5, 30))  # 周六,范围内 → 非交易日


def test_out_of_range_falls_back_to_weekend_rule():
    cal = Calendar(BD)
    # 2026-12-07(周一)在数据范围外 → 按周末规则视为交易日
    assert cal.is_business_day(date(2026, 12, 7))
    assert not cal.is_business_day(date(2026, 12, 6))  # 周日
    assert cal.uses_fallback(date(2026, 12, 7))
    assert not cal.uses_fallback(date(2026, 5, 25))


def test_adjust_modified_following_month_cross_back():
    cal = Calendar(BD)
    # 2026-05-30 周六 → 顺延到 06-01 跨月 → 改往前 05-29(周五)
    assert cal.adjust_modified_following(date(2026, 5, 30)) == date(2026, 5, 29)
    # 2026-06-06 周六 → 顺延到 06-08 周一,未跨月
    assert cal.adjust_modified_following(date(2026, 6, 6)) == date(2026, 6, 8)


def test_adjust_modified_following_month_cross():
    cal = Calendar(BD)
    # 2026-05-31(周日):顺延到 06-01 跨月 → 改为往前到 05-29(周五)
    assert cal.adjust_modified_following(date(2026, 5, 31)) == date(2026, 5, 29)


def test_adjust_business_day_unchanged():
    cal = Calendar(BD)
    assert cal.adjust_modified_following(date(2026, 5, 27)) == date(2026, 5, 27)
