"""GET /api/market:按日预填曲线 + 最新定盘。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import MarketOut
from app.dataio import loader

router = APIRouter(prefix="/api")

BENCH_VALID = {"FR007", "SHIBOR3M"}


@router.get("/market", response_model=MarketOut)
def get_market(benchmark: str = Query(...), date: date = Query(...)):
    if benchmark not in BENCH_VALID:
        raise HTTPException(422, f"不支持的基准: {benchmark}")
    try:  # 三个 loader 调用同读 CSV,统一映射数据错误
        pts = loader.curve_for(benchmark, date)
        fx = loader.fixings_for(benchmark)
        cal = loader.build_calendar()
    except loader.MarketDataError as e:
        raise HTTPException(404, str(e))
    fixing = None
    eligible = [d for d in fx if d <= date]
    if eligible:
        latest = max(eligible)
        fixing = {"date": latest.isoformat(), "rate": round(fx[latest] * 100.0, 6)}
    return MarketOut(
        benchmark=benchmark, valuation_date=date,
        curve=[{"tenor": p.label, "rate": p.rate * 100.0} for p in pts],
        fixing=fixing, calendar_approximate=cal.uses_fallback(date))
