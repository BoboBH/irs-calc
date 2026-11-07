"""IRS 计算器 FastAPI 入口。"""
from __future__ import annotations

from fastapi import FastAPI

from app.api.market import router as market_router
from app.logging_setup import setup_logging

setup_logging()
app = FastAPI(title="IRS Calculator", version="0.1.0")
app.include_router(market_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
