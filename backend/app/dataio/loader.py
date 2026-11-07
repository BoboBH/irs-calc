"""读取 data/ 目录行情文件。

格式约定(与现有文件一致):
- rate_value.csv: Tab 分隔,列 sec_id|date|value;sec_id 含千分位逗号(字符串原样);
  value 为百分数(如 1.3838 → 0.013838)
- rate_info.csv: 列 sec_id|name|sec_code|BMK_IDX|tenor
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS, BenchmarkSpec, tenor_to_months
from app.core.curve import CurvePoint
from app.core.schedule import add_months

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class MarketDataError(ValueError):
    """行情数据缺失或无法解析。"""


def load_value_rows(path: Path | None = None) -> dict[str, dict[date, float]]:
    """返回 {sec_id: {date: rate小数}}。"""
    p = path or (DATA_DIR / "rate_value.csv")
    out: dict[str, dict[date, float]] = {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # 表头
        for sec_id, d, v in reader:
            key = sec_id.strip()
            out.setdefault(key, {})[date.fromisoformat(d)] = float(v) / 100.0
    return out


def load_instruments(path: Path | None = None) -> list[dict]:
    """返回 [{sec_id, name, sec_code, bmk, tenor}]。"""
    p = path or (DATA_DIR / "rate_info.csv")
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for sec_id, name, sec_code, bmk, tenor in reader:
            out.append({"sec_id": sec_id.strip(), "name": name.strip(),
                        "sec_code": sec_code.strip(), "bmk": bmk.strip(),
                        "tenor": tenor.strip()})
    return out


def _tenor_sec_ids(instruments: list[dict], spec: BenchmarkSpec) -> dict[str, str]:
    """该基准下 tenor → sec_id 映射。"""
    m = {i["tenor"]: i["sec_id"] for i in instruments if i["bmk"] == spec.info_bmk}
    missing = set(spec.swap_tenors) - set(m)
    if missing:
        raise MarketDataError(f"{spec.name} 品种表缺少期限: {sorted(missing)}")
    return m


def curve_for(benchmark: str, valuation_date: date) -> list[CurvePoint]:
    """按估值日 + 品种表期限构建曲线点(日期 = 估值日 + 期限)。"""
    spec = BENCHMARKS[benchmark]
    rows = load_value_rows()
    sec_map = _tenor_sec_ids(load_instruments(), spec)
    points = []
    for tenor in spec.swap_tenors:
        sec_id = sec_map[tenor]
        series = rows.get(sec_id, {})
        if valuation_date not in series:
            raise MarketDataError(f"{spec.name} 期限 {tenor} 在 {valuation_date} 无行情")
        points.append(CurvePoint(tenor, add_months(valuation_date, tenor_to_months(tenor)),
                                 series[valuation_date]))
    return points


def fixings_for(benchmark: str) -> dict[date, float]:
    spec = BENCHMARKS[benchmark]
    return load_value_rows().get(spec.fixing_sec_id, {})


def build_calendar() -> Calendar:
    """交易日历 = FR007 定盘有值的日期(银行间真实交易日)。"""
    days = fixings_for("FR007")
    if not days:
        raise MarketDataError("FR007 定盘序列为空,无法构建交易日历")
    return Calendar(set(days))
