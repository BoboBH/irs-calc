from datetime import date
from app.core.conventions import BENCHMARKS, year_fraction, tenor_to_months


def test_fr007_spec():
    spec = BENCHMARKS["FR007"]
    assert spec.fixing_sec_id == "51,557"
    assert spec.day_count == 365
    assert spec.reset_days == 7
    assert spec.float_pay_months == 3
    assert "1M" in spec.swap_tenors and "10Y" in spec.swap_tenors


def test_shibor3m_spec():
    spec = BENCHMARKS["SHIBOR3M"]
    assert spec.fixing_sec_id == "51,558"
    assert spec.day_count == 360
    assert spec.reset_days is None
    assert "1M" not in spec.swap_tenors and "6M" in spec.swap_tenors


def test_year_fraction_act_365():
    assert year_fraction(date(2026, 6, 1), date(2026, 9, 1), 365) == 92 / 365


def test_year_fraction_act_360():
    assert year_fraction(date(2026, 6, 1), date(2026, 9, 1), 360) == 92 / 360


def test_tenor_to_months():
    assert tenor_to_months("1M") == 1
    assert tenor_to_months("9M") == 9
    assert tenor_to_months("1Y") == 12
    assert tenor_to_months("10Y") == 120
