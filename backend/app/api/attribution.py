"""POST /api/attribution 区间归因。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import AttributionRequest, AttributionResponse
from app.api.services import do_attribution, get_calendar
from app.core.pricing import MissingFixingError
from app.dataio.loader import MarketDataError

router = APIRouter(prefix="/api")


@router.post("/attribution", response_model=AttributionResponse)
def post_attribution(req: AttributionRequest):
    if req.start_date is not None and req.start_date >= req.valuation_date:
        raise HTTPException(422, "归因起始日 t0 必须早于估值日 t1")
    if req.effective_date >= req.maturity_date:
        raise HTTPException(400, "起息日必须早于到期日")
    if req.valuation_date > req.maturity_date:
        raise HTTPException(400, "估值日不能晚于到期日")
    calendar = get_calendar()
    try:
        return do_attribution(req, calendar)
    except MissingFixingError as e:
        raise HTTPException(422, f"缺少定盘利率: {e}。请在 fixing_overrides 中提供。")
    except MarketDataError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:  # 内核窗口守卫/坏 tenor 等参数级错误
        raise HTTPException(400, f"参数错误: {e}")
    except OSError as e:  # data/*.csv 缺失
        raise HTTPException(503, f"行情数据不可用: {e}")
