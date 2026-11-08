import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_market_fr007():
    r = client.get("/api/market", params={"benchmark": "FR007", "date": "2026-11-06"})
    assert r.status_code == 200
    body = r.json()
    assert body["benchmark"] == "FR007"
    assert body["valuation_date"] == "2026-11-06"
    assert len(body["curve"]) == 11
    assert body["curve"][0] == {"tenor": "1M", "rate": 1.3838}      # 接口层用百分数
    assert body["fixing"]["date"] == "2026-11-06"
    assert body["fixing"]["rate"] == pytest.approx(1.4)


def test_market_shibor3m():
    r = client.get("/api/market", params={"benchmark": "SHIBOR3M", "date": "2026-11-06"})
    assert r.status_code == 200
    assert len(r.json()["curve"]) == 9


def test_market_missing_date_404():
    r = client.get("/api/market", params={"benchmark": "FR007", "date": "2024-01-01"})
    assert r.status_code == 404
    assert "无行情" in r.json()["detail"]


def test_market_bad_benchmark_422():
    r = client.get("/api/market", params={"benchmark": "SOFR", "date": "2026-11-06"})
    assert r.status_code == 422


def test_market_transition_period_fixing_none_and_calendar_approximate():
    """换算期(曲线已有、FR007 定盘 2025-01-02 才开始):fixing=None + 日历回退标志。

    钉住"最新 ≤ date"取法与 calendar_approximate;换算期真实边界,数据刷新即碎(同其余快照测试)。
    """
    r = client.get("/api/market", params={"benchmark": "FR007", "date": "2024-12-02"})
    assert r.status_code == 200
    body = r.json()
    assert body["fixing"] is None
    assert body["calendar_approximate"] is True


VALUE_REQ = {
    "benchmark": "FR007", "direction": "receiver",
    "notional": 100_000_000, "fixed_rate": 1.65, "spread": 0.0,
    "effective_date": "2026-06-01", "maturity_date": "2026-12-01",
    "fixed_freq_months": 3, "valuation_date": "2026-06-01",
    "curve": [
        {"tenor": "6M", "rate": 1.4}, {"tenor": "1Y", "rate": 1.4},
        {"tenor": "2Y", "rate": 1.4}],
    "fixing_overrides": {"2026-06-01": 1.4},
}


def test_value_matches_core():
    from datetime import date as D, timedelta
    from app.core.calendar import Calendar
    from app.core.conventions import BENCHMARKS
    from app.core.curve import CurvePoint, ZeroCurve
    from app.core.pricing import value_swap

    r = client.post("/api/value", json=VALUE_REQ)
    assert r.status_code == 200
    body = r.json()
    # 与内核直接计算严格一致(双重记账校验)
    d = D(2025, 1, 1)
    cal_days = set()
    while d <= D(2026, 12, 31):
        if d.weekday() < 5:
            cal_days.add(d)
        d += timedelta(days=1)
    cal = Calendar(cal_days)
    curve = ZeroCurve(D(2026, 6, 1), [CurvePoint(t, D(2026, 12, 1) if t == "6M"
                                                  else D(2027, 6, 1) if t == "1Y"
                                                  else D(2028, 6, 1), 0.014)
                                      for t in ("6M", "1Y", "2Y")])
    trade = {"benchmark": "FR007", "direction": "receiver", "notional": 1e8,
             "fixed_rate": 0.0165, "spread": 0.0, "effective_date": D(2026, 6, 1),
             "maturity_date": D(2026, 12, 1), "fixed_freq_months": 3}
    expect = value_swap(trade, D(2026, 6, 1), curve, cal, BENCHMARKS["FR007"],
                        fixings={D(2026, 6, 1): 0.014})
    assert body["npv"] == pytest.approx(expect["npv"])
    assert body["pv_fixed"] > body["pv_floating"]
    assert body["cashflows"]["fixed"][0]["rate"] == pytest.approx(1.65)
    assert body["cashflows"]["floating"][0]["sub_periods"][0]["source"] == "fixing"


def test_value_missing_fixing_422():
    """起息/估值早于定盘序列起点(真实数据自 2025-01-02 起),overrides 为空 → 422。
    (原 2026-06-01 场景不成立:真实定盘在该日存在,合并后不会缺失——实测。)"""
    bad = {**VALUE_REQ, "effective_date": "2024-12-02", "valuation_date": "2024-12-02",
           "maturity_date": "2025-06-01", "fixing_overrides": {}}
    r = client.post("/api/value", json=bad)
    assert r.status_code == 422
    assert "定盘" in r.json()["detail"]


def test_value_stale_fixing_warning():
    """估值日 2026-11-20 晚于定盘序列末尾(真实数据止于 2026-11-06,缺口 14 天 > 11)
    → warnings 含定盘陈旧告警(Task 11 移交项 1);且 11-20 < 到期日,ex-coupon 下
    尚有 12-01 支付 → npv≠0(原 12-01 场景等于到期日,现金流全被剔除,npv 恒 0)。"""
    req = {**VALUE_REQ, "valuation_date": "2026-11-20"}
    r = client.post("/api/value", json=req)
    assert r.status_code == 200
    body = r.json()
    assert any("定盘陈旧" in w for w in body["warnings"])
    assert body["npv"] != 0


def test_value_bad_tenor_400():
    """显式曲线含非法 tenor("3Q")→ 400 字段级错误,不得 500(Task 11 移交项 2)。"""
    req = {**VALUE_REQ, "curve": [{"tenor": "3Q", "rate": 1.4},
                                  {"tenor": "6M", "rate": 1.4},
                                  {"tenor": "1Y", "rate": 1.4},
                                  {"tenor": "2Y", "rate": 1.4}]}
    r = client.post("/api/value", json=req)
    assert r.status_code == 400


def test_attribution_identity_ok():
    """窗口 (06-01, 06-05] 内无新重置(周网格 06-01/06-08)→ 定盘-远期楔子不进 ε,
    identity_ok=True。原 06-08 场景:窗口含 06-08 重置,npv_t1 用真实定盘 1.41 而
    npv_static 用静态远期 ≈1.3996,一阶楔子 ≈−191 元按白皮书 §4.7 口径进残差,
    残差门(5%·max(|ΔNPV|,|Curve|,1))如实拒绝——计算正确,是场景选在了楔子上;
    门与楔子的设计取舍记收尾清单。"""
    req = {**VALUE_REQ,
           "start_date": "2026-06-01", "valuation_date": "2026-06-05",
           "effective_date": "2026-06-01", "maturity_date": "2028-06-01",
           "fixing_overrides": {"2026-06-01": 1.4}}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["identity"]["ok"] is True
    assert set(body["components"]) == {"theta", "carry", "roll", "curve", "spread", "residual"}
    assert body["cf"] == pytest.approx(0.0)


def test_attribution_bad_dates_422():
    req = {**VALUE_REQ, "start_date": "2026-06-08", "valuation_date": "2026-06-01"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 422


def test_attribution_market_curve_curve_component_nonzero():
    """空曲线(自动从行情加载两日真实曲线)→ curve 分量非零、detail 非空。
    装配层接线钉住:显式曲线模式下两日同形 curve≡0,curve_t0/t1 互换也能全绿,
    必须用市场曲线模式钉装配。"""
    req = {**VALUE_REQ, "curve": [],
           "start_date": "2026-06-01", "valuation_date": "2026-11-06",
           "effective_date": "2026-06-01", "maturity_date": "2028-06-01",
           "fixing_overrides": {}}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["components"]["curve"] != 0
    assert len(body["detail"]) > 0


def test_attribution_window_outside_life_400():
    """窗口 (start, end] 与存续期无交集(end ≤ effective)→ 内核窗口守卫
    ValueError → 400(装配层错误映射钉住;start 越过到期的场景已被路由
    valuation>maturity 守卫前置拦截,内核该分支经 API 不可达)。"""
    req = {**VALUE_REQ, "start_date": "2026-06-01", "valuation_date": "2026-06-02",
           "effective_date": "2026-06-05", "maturity_date": "2026-12-01"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 400


def test_attribution_valuation_beyond_maturity_400():
    """估值日晚于到期日 → 400(与 /api/value 对称;此前会 200 产出已到期合约的归因)。"""
    req = {**VALUE_REQ, "start_date": "2026-06-01", "valuation_date": "2027-01-10"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 400


ATTR_AUTO_REQ = {**VALUE_REQ, "curve": [], "valuation_date": "2026-11-06",
                 "effective_date": "2026-06-01", "maturity_date": "2028-06-01",
                 "fixing_overrides": {}}


def test_attribution_default_window_prev_trading_day():
    """无 start_date、T=2026-11-06(数据末个交易日)→ 默认 t0=2026-11-05(行情中 max(d<T)),
    结果与显式传同一 t0 完全一致,且各分量非全零。"""
    r_def = client.post("/api/attribution", json=ATTR_AUTO_REQ)
    assert r_def.status_code == 200
    b_def = r_def.json()
    r_exp = client.post("/api/attribution", json={**ATTR_AUTO_REQ, "start_date": "2026-11-05"})
    assert r_exp.status_code == 200
    b_exp = r_exp.json()
    assert b_def["cf"] == pytest.approx(b_exp["cf"])
    assert b_def["delta_npv"] == pytest.approx(b_exp["delta_npv"])
    for k in b_def["components"]:
        assert b_def["components"][k] == pytest.approx(b_exp["components"][k]), k
    assert b_def["detail"] == b_exp["detail"]
    assert b_def["identity"] == b_exp["identity"]
    assert b_def["delta_npv"] != 0
    assert any(v != 0 for v in b_def["components"].values())


def test_attribution_default_window_non_trading_t_zero_response():
    """无 start_date、T=2026-11-07(周六,行情无此日)→ 200 全零归因(结构逐字段与正常
    一致:金额/效应 0、明细空表、identity ok/diff=0),warnings 含非交易日说明。"""
    req = {**VALUE_REQ, "valuation_date": "2026-11-07"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 200
    b = r.json()
    assert b["delta_npv"] == 0.0
    assert b["cf"] == 0.0
    assert b["components"] == {"theta": 0.0, "carry": 0.0, "roll": 0.0,
                               "curve": 0.0, "spread": 0.0, "residual": 0.0}
    assert b["identity"] == {"ok": True, "diff": 0.0}
    assert b["detail"] == []
    vt = b["valuation_t1"]
    assert vt["npv"] == 0.0 and vt["pv_fixed"] == 0.0 and vt["pv_floating"] == 0.0
    assert vt["dv01_parallel"] == 0.0
    assert vt["krdv01"] == [] and vt["cashflows"] == {"fixed": [], "floating": []}
    assert any("非交易日" in w and "2026-11-07" in w for w in b["warnings"])


def test_attribution_default_window_earliest_trading_day_404():
    """无 start_date、T=数据最早可得交易日 2024-11-08(更早无任何全期限行情日)
    → 404,detail 含"无更早行情"。"""
    req = {**ATTR_AUTO_REQ, "valuation_date": "2024-11-08"}
    r = client.post("/api/attribution", json=req)
    assert r.status_code == 404
    assert "无更早行情" in r.json()["detail"]
