from datetime import date
import pytest
from app.core.conventions import BENCHMARKS
from app.dataio.loader import (MarketDataError, build_calendar, curve_for,
                               fixings_for, load_instruments, load_value_rows)


def test_load_value_rows_parses_comma_secid_and_percent():
    rows = load_value_rows()
    # sec_id 含千分位逗号,按字符串键;value 为百分数 → 小数
    assert rows["51,557"][date(2026, 11, 6)] == pytest.approx(0.014)
    assert len(rows["51,557"]) == 457


def test_load_instruments():
    ins = load_instruments()
    # 品种表同一 BMK_IDX 下还含定盘行(51,557/tenor=7D、51,558/tenor=3M),
    # 互换品种按 tenor ∈ swap_tenors 过滤
    fr = [i for i in ins if i["bmk"] == "CNY-FR007"
          and i["tenor"] in BENCHMARKS["FR007"].swap_tenors]
    assert len(fr) == 11
    assert any(i["tenor"] == "10Y" and i["sec_id"] == "249,305" for i in fr)


def test_curve_for_fr007_20261106():
    pts = curve_for("FR007", date(2026, 11, 6))
    assert [p.label for p in pts] == list(BENCHMARKS["FR007"].swap_tenors)
    assert pts[0].label == "1M"
    assert pts[0].rate == pytest.approx(0.013838)
    assert pts[0].date == date(2026, 12, 6)     # 估值日 2026-11-06 + 1M
    assert pts[-1].label == "10Y"
    assert pts[-1].rate == pytest.approx(0.019)


def test_curve_for_shibor3m():
    pts = curve_for("SHIBOR3M", date(2026, 11, 6))
    assert len(pts) == 9
    assert pts[0].label == "6M"


def test_curve_for_missing_date_raises():
    with pytest.raises(MarketDataError):
        curve_for("FR007", date(2024, 1, 1))


def test_fixings_for_fr007_and_shibor3m():
    fx = fixings_for("FR007")
    assert len(fx) == 457
    assert fx[date(2025, 1, 2)] == pytest.approx(0.018)
    assert fx[date(2026, 11, 6)] == pytest.approx(0.014)
    fx2 = fixings_for("SHIBOR3M")
    assert fx2[date(2026, 11, 6)] == pytest.approx(0.01398)


def test_build_calendar_from_fr007_fixing_dates():
    cal = build_calendar()
    assert cal.is_business_day(date(2026, 11, 6))    # 周五,有定盘
    assert not cal.is_business_day(date(2026, 11, 7))  # 周六
    assert cal.uses_fallback(date(2027, 1, 1))       # 数据范围外
    assert not cal.uses_fallback(date(2026, 11, 6))
