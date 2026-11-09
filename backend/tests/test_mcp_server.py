"""MCP 服务器注册面:4 个工具与 API 字段同名同义(纯注册检查,不触发 HTTP;
HTTP 行为由 test_api.py 全量覆盖)。"""
import pytest

from app.mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_four_tools_registered_with_trade_params():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert set(tools) == {"load_market", "value_swap", "campisi_attribution", "par_rate"}

    # 交易参数与 TradeRequest 字段 1:1(同名同义:利率 % / 利差 bp / ISO 日期)
    props = tools["value_swap"].inputSchema["properties"]
    for f in ("benchmark", "direction", "notional", "fixed_rate", "spread_bp",
              "effective_date", "maturity_date", "valuation_date", "fixed_freq_months",
              "curve", "fixing_overrides", "discount_basis", "curve_interp",
              "fixing_lag_bd", "principal_exchange"):
        assert f in props, f

    # 归因独有 start_date(缺省自动 T-1);估值无
    assert "start_date" in tools["campisi_attribution"].inputSchema["properties"]
    assert "start_date" not in props

    # 平价不参与方向/名义/固定利率(线性消去)
    par_props = tools["par_rate"].inputSchema["properties"]
    for f in ("fixed_rate", "direction", "notional"):
        assert f not in par_props, f

    # docstring 带单位口径(agent 可见的第一文档)
    assert "基点" in tools["value_swap"].description
    assert "百分数" in tools["value_swap"].description
    assert "Campisi" in tools["campisi_attribution"].description
