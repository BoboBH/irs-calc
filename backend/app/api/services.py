"""请求 ↔ 内核转换层:单位换算(百分点↔小数)、数据装配、错误映射。"""
from __future__ import annotations

from datetime import date

from app.core import risk
from app.core.attribution import run_attribution
from app.core.calendar import Calendar
from app.core.conventions import BENCHMARKS, tenor_to_months
from app.core.curve import CurvePoint, ZeroCurve
from app.core.pricing import value_swap
from app.core.schedule import add_months
from app.dataio import loader
from app.dataio.loader import MarketDataError
from app.api.schemas import AttributionRequest, TradeRequest


def get_calendar() -> Calendar:
    return loader.build_calendar()


def load_fixings(benchmark: str, overrides: dict[date, float] | None = None) -> dict[date, float]:
    fx = dict(loader.fixings_for(benchmark))
    for d, v in (overrides or {}).items():
        fx[d] = v / 100.0
    return fx


def build_curve(benchmark: str, valuation_date: date,
                curve_in: list | None) -> ZeroCurve:
    if curve_in:
        pts = [CurvePoint(p.tenor, add_months(valuation_date, tenor_to_months(p.tenor)), p.rate / 100.0)
               for p in curve_in]
        return ZeroCurve(valuation_date, pts)
    return ZeroCurve(valuation_date, loader.curve_for(benchmark, valuation_date))


def request_to_trade(req: TradeRequest) -> dict:
    return {
        "benchmark": req.benchmark,
        "direction": req.direction,
        "notional": req.notional,
        "fixed_rate": req.fixed_rate / 100.0,
        "spread": req.spread / 100.0,
        "effective_date": req.effective_date,
        "maturity_date": req.maturity_date,
        "fixed_freq_months": req.fixed_freq_months,
    }


def do_value(req: TradeRequest, calendar: Calendar) -> dict:
    spec = BENCHMARKS[req.benchmark]
    trade = request_to_trade(req)
    curve = build_curve(req.benchmark, req.valuation_date, req.curve)
    fixings = load_fixings(req.benchmark, req.fixing_overrides)
    warnings = []
    if not req.curve:
        pass  # 曲线来自行情;坏点不清洗(用户决策),界面可改
    if req.effective_date <= req.valuation_date:
        # 仅当浮动腿可能已取用定盘(首重置=起息日 ≤ 估值日)才查陈旧,
        # 全远期(起息晚于估值日)不发告警;阈值 11 天:实测定盘序列最长间隔
        # 10 天(春节/国庆 8-10 天),再大才是真陈旧
        prior = [d for d in fixings if d <= req.valuation_date]
        if prior:
            latest_fx = max(prior)
            gap = (req.valuation_date - latest_fx).days
            if gap > 11:
                warnings.append(
                    f"定盘陈旧:最新定盘 {latest_fx.isoformat()} 距估值日 {gap} 天,浮动腿定价可能与市场偏离")
        else:
            warnings.append("估值日早于定盘序列起点,浮动腿利率主要来自曲线远期")
    val = value_swap(trade, req.valuation_date, curve, calendar, spec, fixings=fixings)
    dv = risk.parallel_dv01(trade, req.valuation_date, curve, calendar, spec, fixings=fixings)
    keys = risk.key_tenors_for(curve, req.maturity_date)
    parts = risk.krdv01(trade, req.valuation_date, curve, calendar, spec,
                        fixings=fixings, key_tenors=keys)
    return {
        "npv": val["npv"],
        "pv_fixed": val["pv_fixed"],
        "pv_floating": val["pv_floating"],
        "dv01_parallel": dv,
        "krdv01": [{"tenor": x["tenor"], "dv01": x["dv01"]} for x in parts],
        "cashflows": {
            "fixed": _rows(val["fixed_rows"]),
            "floating": _rows(val["floating_rows"]),
        },
        "warnings": warnings,
    }


def _rows(rows):
    return [{
        "pay_date": r.pay_date.isoformat(),
        "accrual_start": r.accrual_start.isoformat(),
        "accrual_end": r.accrual_end.isoformat(),
        "days": r.days,
        "tau": r.tau,
        "rate": r.rate * 100.0,
        "amount": r.amount,
        "df": r.df,
        "pv": r.pv,
        "sub_periods": [{
            "reset_date": sp.reset_date.isoformat(),
            "accrual_start": sp.accrual_start.isoformat(),
            "accrual_end": sp.accrual_end.isoformat(),
            "days": sp.days,
            "tau": sp.tau,
            "rate": sp.rate * 100.0,
            "source": sp.source,
        } for sp in r.sub_periods],
    } for r in rows]


def _zero_attribution(valuation_date: date) -> dict:
    """估值日非交易日(无行情)的全零归因:结构与 AttributionResponse 逐字段一致,
    不进内核;金额/效应分量置 0、曲线效应明细空表、勾稽门放行。"""
    return {
        "delta_npv": 0.0,
        "cf": 0.0,
        "components": {"theta": 0.0, "carry": 0.0, "roll": 0.0,
                       "curve": 0.0, "spread": 0.0, "residual": 0.0},
        "identity": {"ok": True, "diff": 0.0},
        "detail": [],
        "valuation_t1": {
            "npv": 0.0, "pv_fixed": 0.0, "pv_floating": 0.0,
            "dv01_parallel": 0.0, "krdv01": [],
            "cashflows": {"fixed": [], "floating": []},
            "warnings": [],
        },
        "warnings": [f"估值日 {valuation_date.isoformat()} 非交易日(无行情),归因各分项为 0"],
    }


def do_attribution(req: AttributionRequest, calendar: Calendar) -> dict:
    spec = BENCHMARKS[req.benchmark]
    trade = request_to_trade(req)
    start = req.start_date
    if start is None:
        # 默认窗口 [T-1, T]:t1 无行情 → 全零归因(200 + 告警);有 T 无更早行情 → 404
        dates = loader.available_curve_dates(req.benchmark)
        if req.valuation_date not in dates:
            return _zero_attribution(req.valuation_date)
        prior = [d for d in dates if d < req.valuation_date]
        if not prior:
            raise MarketDataError(f"估值日 {req.valuation_date} 无更早行情,无法构造 T-1")
        start = prior[-1]
    curve_t0 = build_curve(req.benchmark, start, req.curve)
    curve_t1 = build_curve(req.benchmark, req.valuation_date, req.curve)
    fixings = load_fixings(req.benchmark, req.fixing_overrides)
    res = run_attribution(trade=trade, start_date=start, end_date=req.valuation_date,
                          curve_t0=curve_t0, curve_t1=curve_t1, fixings=fixings,
                          calendar=calendar, spec=spec)
    value_part = do_value(req, calendar)
    return {
        "delta_npv": res.delta_npv,
        "cf": res.cf,
        "components": {"theta": res.theta, "carry": res.carry, "roll": res.roll,
                       "curve": res.curve_effect, "spread": res.spread,
                       "residual": res.residual},
        "identity": {"ok": res.identity_ok, "diff": res.identity_diff},
        "detail": res.detail,
        "valuation_t1": value_part,
        "warnings": res.warnings,
    }
