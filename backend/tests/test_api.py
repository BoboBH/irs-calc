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
