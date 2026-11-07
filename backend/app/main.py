"""IRS 计算器 FastAPI 入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.attribution import router as attribution_router
from app.api.market import router as market_router
from app.api.valuation import router as value_router
from app.logging_setup import setup_logging

setup_logging()
app = FastAPI(title="IRS Calculator", version="0.1.0")
app.include_router(market_router)
app.include_router(value_router)
app.include_router(attribution_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
