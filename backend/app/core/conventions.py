"""基准利率市场惯例配置(设计文档 §4.3)。"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BenchmarkSpec:
    name: str              # FR007 / SHIBOR3M
    info_bmk: str          # rate_info.csv 的 BMK_IDX 值
    fixing_sec_id: str     # 定盘序列的 sec_id(注意含千分位逗号)
    day_count: int         # 浮动腿计息基数
    fixed_day_count: int   # 固定腿计息基数
    fixed_freq_months: int  # 固定腿默认付息频率(月)
    float_pay_months: int  # 浮动腿付息频率(月)
    reset_days: int | None  # FR007=7(周重置);SHIBOR3M=None(按期初重置)
    swap_tenors: tuple[str, ...]


BENCHMARKS: dict[str, BenchmarkSpec] = {
    "FR007": BenchmarkSpec(
        name="FR007",
        info_bmk="CNY-FR007",
        fixing_sec_id="51,557",
        day_count=365,
        fixed_day_count=365,
        fixed_freq_months=3,
        float_pay_months=3,
        reset_days=7,
        swap_tenors=("1M", "3M", "6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"),
    ),
    "SHIBOR3M": BenchmarkSpec(
        name="SHIBOR3M",
        info_bmk="CNY-SHIBOR-3M",
        fixing_sec_id="51,558",
        day_count=360,
        fixed_day_count=360,
        fixed_freq_months=3,
        float_pay_months=3,
        reset_days=None,
        swap_tenors=("6M", "9M", "1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"),
    ),
}


def year_fraction(start: date, end: date, day_count: int) -> float:
    """ACT/n 年化计息期限。"""
    return (end - start).days / day_count


def tenor_to_months(tenor: str) -> int:
    """'1M'->1, '9M'->9, '1Y'->12, '10Y'->120。"""
    t = tenor.strip().upper()
    if t.endswith("M"):
        return int(t[:-1])
    if t.endswith("Y"):
        return int(t[:-1]) * 12
    raise ValueError(f"无法解析期限: {tenor!r}")
