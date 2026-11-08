"""API 请求/响应模型。接口层利率一律用百分数(1.65 = 1.65%)、浮动端利差一律用基点
(spread_bp,25 = 25bp),内核层用小数;换算在装配层完成(/100、/10000)。"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CurvePointIn(BaseModel):
    tenor: str
    rate: float  # %


class MarketOut(BaseModel):
    benchmark: str
    valuation_date: date
    curve: list[CurvePointIn]
    fixing: dict | None = None        # {"date": "2026-11-06", "rate": 1.4}(%)
    calendar_approximate: bool = False


class TradeRequest(BaseModel):
    benchmark: Literal["FR007", "SHIBOR3M"]
    direction: Literal["receiver", "payer"]
    notional: float = Field(gt=0)
    fixed_rate: float                  # %
    spread_bp: float = 0.0             # bp(基点),叠加在基准指标之上;内核 = spread_bp/10000
    effective_date: date
    maturity_date: date
    fixed_freq_months: int = Field(default=3, ge=1, le=12)
    valuation_date: date
    curve: list[CurvePointIn] = []     # 空 = 按估值日自动从行情加载;期限支持 7D 等日历日标签
    fixing_overrides: dict[date, float] = {}  # {"2026-11-05": 1.37}(%);ISO 串自动转 date,坏串 422
    discount_basis: Literal["simple", "cont"] = "simple"  # 贴现:单利(白皮书)/连续复利(厂商对账)
    curve_interp: Literal["linear", "hermite"] = "linear"  # 曲线插值:零利率线性(厂商对齐)/单调三次 Hermite
    fixing_lag_bd: int = Field(default=0, ge=0, le=5)     # 定盘观察日前推营业日数;0=当日,1=T-1(厂商口径)
    principal_exchange: bool = False                      # 到期两腿互换本金,不含首期(厂商口径)


class AttributionRequest(TradeRequest):
    start_date: date | None = None     # t0;缺省 = 默认窗口,自动取行情中 T-1 = max(d < T)


class Krdv01Out(BaseModel):
    tenor: str
    dv01: float


class ValueResponse(BaseModel):
    npv: float
    pv_fixed: float
    pv_floating: float
    dv01_parallel: float
    krdv01: list[Krdv01Out]
    cashflows: dict                    # {"fixed": [...], "floating": [...]}
    warnings: list[str]


class AttributionResponse(BaseModel):
    delta_npv: float
    cf: float
    components: dict                   # theta/carry/roll/curve/spread/residual
    identity: dict                     # {"ok": bool, "diff": float}
    detail: list[dict]
    valuation_t1: ValueResponse
    warnings: list[str]
