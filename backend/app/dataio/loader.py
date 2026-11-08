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
    """返回 {sec_id: {date: rate小数}}。无法解析的行抛 MarketDataError(含文件名与行号)。"""
    p = path or (DATA_DIR / "rate_value.csv")
    out: dict[str, dict[date, float]] = {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # 表头
        for n, row in enumerate(reader, start=2):
            try:
                sec_id, d, v = row
                key = sec_id.strip()
                out.setdefault(key, {})[date.fromisoformat(d)] = float(v) / 100.0
            except ValueError as e:
                raise MarketDataError(f"{p.name} 第{n}行无法解析: {row!r}({e})") from None
    return out


def load_instruments(path: Path | None = None) -> list[dict]:
    """返回 [{sec_id, name, sec_code, bmk, tenor}]。"""
    p = path or (DATA_DIR / "rate_info.csv")
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for n, row in enumerate(reader, start=2):
            try:
                sec_id, name, sec_code, bmk, tenor = row
            except ValueError:
                raise MarketDataError(f"{p.name} 第{n}行无法解析: {row!r}") from None
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


def available_curve_dates(benchmark: str) -> list[date]:
    """该基准全部互换期限都有行情的日期集(升序)。

    与 curve_for 的可用性口径一致(任一期限缺值的日子不算,如数据初期的
    部分覆盖日);供归因默认窗口 T-1 = max(d < T) 查询,单次读盘。"""
    spec = BENCHMARKS[benchmark]
    rows = load_value_rows()
    sec_map = _tenor_sec_ids(load_instruments(), spec)
    common = set.intersection(*(set(rows.get(sec_map[t], {})) for t in spec.swap_tenors))
    return sorted(common)


def fixings_for(benchmark: str) -> dict[date, float]:
    spec = BENCHMARKS[benchmark]
    return load_value_rows().get(spec.fixing_sec_id, {})


def build_calendar() -> Calendar:
    """交易日历 = FR007 定盘有值的日期(银行间真实交易日)。"""
    days = fixings_for("FR007")
    if not days:
        raise MarketDataError("FR007 定盘序列为空,无法构建交易日历")
    return Calendar(set(days))
