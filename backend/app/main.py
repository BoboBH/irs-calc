"""IRS 计算器 FastAPI 入口(API + MCP streamable HTTP 同端口)。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.attribution import router as attribution_router
from app.api.market import router as market_router
from app.api.par_rate import router as par_rate_router
from app.api.valuation import router as value_router
from app.logging_setup import setup_logging
from app.mcp_server import mcp

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # MCP streamable HTTP 的会话管理器随服务启停(挂载子应用的 lifespan 不会自动执行)
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="IRS Calculator", version="0.1.0", lifespan=lifespan)
app.include_router(market_router)
app.include_router(value_router)
app.include_router(attribution_router)
app.include_router(par_rate_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# MCP streamable HTTP(/mcp):借入其路由,置于 /api 之后、前端静态挂载之前;
# 端点 = http://127.0.0.1:8000/mcp,与 API 同端口同进程
for _r in mcp.streamable_http_app().routes:
    app.router.routes.append(_r)

_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
