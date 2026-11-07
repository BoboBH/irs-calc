"""POST /api/value 单日估值。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import TradeRequest, ValueResponse
from app.api.services import do_value, get_calendar
from app.core.pricing import MissingFixingError
from app.dataio.loader import MarketDataError

router = APIRouter(prefix="/api")


@router.post("/value", response_model=ValueResponse)
def post_value(req: TradeRequest):
    if req.effective_date >= req.maturity_date:
        raise HTTPException(400, "起息日必须早于到期日")
    if req.valuation_date > req.maturity_date:
        raise HTTPException(400, "估值日不能晚于到期日")
    calendar = get_calendar()
    try:
        return do_value(req, calendar)
    except MissingFixingError as e:
        raise HTTPException(422, f"缺少定盘利率: {e}。请在 fixing_overrides 中提供。")
    except MarketDataError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:  # 坏 tenor(tenor_to_months/ZeroCurve 重复点)等参数级错误
        raise HTTPException(400, f"参数错误: {e}")
    except OSError as e:  # data/*.csv 缺失(Task 11 移交项 3)
        raise HTTPException(503, f"行情数据不可用: {e}")
