"""IRS 计算器 MCP 服务器:把本服务的 HTTP API 1:1 包装成 MCP 工具,供 AI agent 调用。

前置:先启动后端(uvicorn app.main:app --port 8000),本服务器只是薄封装,
口径(schema 校验/缺省值/定盘加载/错误映射)全部以 API 为唯一真源,不在本地重复实现。

单位口径(与 API 一致,工具参数同名同义):
- 利率一律百分数:fixed_rate=1.65 即 1.65%;曲线点 rate 同;
- 浮动端利差一律基点:spread_bp=25 即 25bp;
- 日期一律 ISO 串:"2026-11-06";
- curve 空 = 按估值日自动加载行情曲线(agent 最省事的用法);
- fixing_lag_bd 缺省 1 = 合约标准 T-1 定盘(CFETS 标准合约要素);
- 页面默认口径为贴现 cont + 本金交割 principal_exchange=True,对账页面时显式传同名参数。

启动(stdio):backend/.venv/Scripts/python.exe -m app.mcp_server
Claude Code 注册:claude mcp add irs-calc -- <venv 绝对路径>/python.exe -m app.mcp_server
(工作目录需在 backend/,或用绝对路径;-m app.mcp_server 依赖 cwd 含 app 包)
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("IRS_API_BASE", "http://127.0.0.1:8000").rstrip("/")

mcp = FastMCP(
    "irs-calc",
    instructions=(
        "银行间利率互换(IRS)计算器:FR007/Shibor 3M 单笔合约的估值(NPV/DV01/现金流)、"
        "Campisi 日频归因、平价利率、行情曲线与定盘查询。"
        "利率单位一律百分数(1.65 = 1.65%),利差一律基点(25 = 25bp),日期一律 ISO 串。"
        "curve 传空数组即按估值日自动加载行情曲线,最省事;"
        "缺省口径为合约标准 T-1 定盘(fixing_lag_bd=1)、单利贴现、不含本金交割,"
        "与前端页面对账需显式传 discount_basis='cont'、principal_exchange=True。"
        "所有工具要求本服务已启动(默认 http://127.0.0.1:8000)。"
    ),
)


def _get(path: str, params: dict) -> dict:
    try:
        r = httpx.get(f"{API}{path}", params=params, timeout=60)
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"IRS 计算器服务不可达({API}):请先启动后端 "
            f"cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000"
        ) from e
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.json().get('detail', r.text)}")
    return r.json()


def _post(path: str, payload: dict) -> dict:
    try:
        r = httpx.post(f"{API}{path}", json=payload, timeout=60)
    except httpx.ConnectError as e:
        raise RuntimeError(
            f"IRS 计算器服务不可达({API}):请先启动后端 "
            f"cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000"
        ) from e
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.json().get('detail', r.text)}")
    return r.json()


@mcp.tool()
def load_market(benchmark: str, date: str) -> dict:
    """加载行情:曲线报价点 + 当期定盘。

    Args:
        benchmark: 基准指标,"FR007" 或 "SHIBOR3M"
        date: 行情日期,ISO 串(如 "2026-11-06")

    Returns:
        {benchmark, valuation_date, curve: [{tenor, rate(%)}], fixing: {date, rate(%)} | null,
         calendar_approximate};fixing=None 表示该日早于定盘序列起点。
        curve 点即 POST 估值/归因/平价时 curve 参数的行格式。
    """
    return _get("/api/market", {"benchmark": benchmark, "date": date})


def _trade_args(
    benchmark: str,
    effective_date: str,
    maturity_date: str,
    valuation_date: str,
    fixed_rate: float = 1.65,
    spread_bp: float = 0.0,
    notional: float = 100_000_000,
    direction: str = "receiver",
    fixed_freq_months: int = 3,
    curve: list[dict] | None = None,
    fixing_overrides: dict[str, float] | None = None,
    discount_basis: str = "simple",
    curve_interp: str = "linear",
    fixing_lag_bd: int = 1,
    principal_exchange: bool = False,
) -> dict:
    """收集 TradeRequest 同名参数为 API payload(工具签名与 API 字段 1:1)。"""
    return {
        "benchmark": benchmark, "direction": direction, "notional": notional,
        "fixed_rate": fixed_rate, "spread_bp": spread_bp,
        "effective_date": effective_date, "maturity_date": maturity_date,
        "fixed_freq_months": fixed_freq_months, "valuation_date": valuation_date,
        "curve": curve or [], "fixing_overrides": fixing_overrides or {},
        "discount_basis": discount_basis, "curve_interp": curve_interp,
        "fixing_lag_bd": fixing_lag_bd, "principal_exchange": principal_exchange,
    }


@mcp.tool()
def value_swap(
    benchmark: str,
    effective_date: str,
    maturity_date: str,
    valuation_date: str,
    fixed_rate: float = 1.65,
    spread_bp: float = 0.0,
    notional: float = 100_000_000,
    direction: str = "receiver",
    fixed_freq_months: int = 3,
    curve: list[dict] | None = None,
    fixing_overrides: dict[str, float] | None = None,
    discount_basis: str = "simple",
    curve_interp: str = "linear",
    fixing_lag_bd: int = 1,
    principal_exchange: bool = False,
) -> dict:
    """估值:单笔 IRS 的 NPV、两腿现值、平行/关键期限 DV01、逐笔现金流。

    Args:
        benchmark: "FR007" 或 "SHIBOR3M"
        effective_date / maturity_date / valuation_date: 起息/到期/估值日,ISO 串;估值日须 ≤ 到期日
        fixed_rate: 固定利率,百分数(1.65 = 1.65%)
        spread_bp: 浮动端利差,基点(25 = 25bp),叠加在基准指标之上
        notional: 名义本金(元)
        direction: "receiver"(收固定付浮动)或 "payer"
        fixed_freq_months: 固定腿支付周期(月,1-12,默认 3);浮动端随基准(FR007 周/Shibor 3M 季)
        curve: 零息曲线点 [{tenor, rate(%)}];**传空 = 按估值日自动加载行情曲线**
        fixing_overrides: 已定盘利率覆盖 {ISO日期: rate(%)};一般留空(自动加载定盘序列)
        discount_basis: 贴现口径 "simple"(单利,缺省)或 "cont"(连续复利,前端页面默认)
        curve_interp: 曲线插值 "linear"(缺省,厂商对齐)或 "hermite"(中债官方同款)
        fixing_lag_bd: 定盘观察日前推营业日数;1=合约标准 T-1(缺省),0=当日(旧取法)
        principal_exchange: 到期是否两腿互换本金(前端页面默认 True)

    Returns:
        {npv, pv_fixed, pv_floating, dv01_parallel, krdv01: [{tenor, dv01}],
         cashflows: {fixed: [...], floating: [...]}, warnings: [...]}(金额均元)
    """
    return _post("/api/value", _trade_args(
        benchmark, effective_date, maturity_date, valuation_date, fixed_rate,
        spread_bp, notional, direction, fixed_freq_months, curve, fixing_overrides,
        discount_basis, curve_interp, fixing_lag_bd, principal_exchange))


@mcp.tool()
def campisi_attribution(
    benchmark: str,
    effective_date: str,
    maturity_date: str,
    valuation_date: str,
    start_date: str | None = None,
    fixed_rate: float = 1.65,
    spread_bp: float = 0.0,
    notional: float = 100_000_000,
    direction: str = "receiver",
    fixed_freq_months: int = 3,
    curve: list[dict] | None = None,
    fixing_overrides: dict[str, float] | None = None,
    discount_basis: str = "simple",
    curve_interp: str = "linear",
    fixing_lag_bd: int = 1,
    principal_exchange: bool = False,
) -> dict:
    """Campisi 日频归因:把估值窗口 (start_date, valuation_date] 内的 ΔNPV 分解为
    theta/carry/roll/curve/spread/residual 各因子(白皮书口径)。

    因子含义:theta = 静态曲线推进的总时间效应(npv_static + cf − npv_t0),
    其中 carry = 票息效应(固定利息 − 浮动 L0+spread 计提),roll = theta − carry(骑乘);
    curve = 关键期限 KRDV01 × 曲线变动之和(detail 含逐关键期限明细);
    spread 单曲线口径恒 0;residual = ΔNPV − 各因子之和;
    components 恒满足 ΔNPV = theta+carry+roll+curve+spread+residual;
    identity.ok=False 表示残差门(5%·max(|ΔNPV|,|Curve|,1))拒绝——一阶分解在该
    窗口/口径下不干净(如 curve=[] 自动加载两日真实行情曲线且曲线大幅移动时),
    因子仍可用但应谨慎,可改传显式 curve(两日同形 → curve≡0、residual≈0)。
    curve 两种模式:显式曲线 = 两日同形(静态口径,curve 恒 0);
    curve=[] = 自动加载 t0/T 两日真实行情曲线(真实曲线效应)。

    Args:
        除 start_date 外与 value_swap 同名同义。
        start_date: 窗口起点 t0(ISO 串);**留空 = 自动取行情中估值日的前一交易日**

    Returns:
        {delta_npv, cf(窗口内已支付现金流), components: {theta, carry, roll, curve,
         spread, residual}, detail: [逐关键期限], identity: {ok, diff},
         valuation_t1: 窗口末全量估值(同 value_swap 返回), warnings: [...]}
        valuation_date 为非交易日时返回全零归因 + 非交易日 warning(正常语义,非错误)。
    """
    payload = _trade_args(
        benchmark, effective_date, maturity_date, valuation_date, fixed_rate,
        spread_bp, notional, direction, fixed_freq_months, curve, fixing_overrides,
        discount_basis, curve_interp, fixing_lag_bd, principal_exchange)
    if start_date is not None:
        payload["start_date"] = start_date
    return _post("/api/attribution", payload)


@mcp.tool()
def par_rate(
    benchmark: str,
    effective_date: str,
    maturity_date: str,
    valuation_date: str,
    spread_bp: float = 0.0,
    fixed_freq_months: int = 3,
    curve: list[dict] | None = None,
    fixing_overrides: dict[str, float] | None = None,
    discount_basis: str = "simple",
    curve_interp: str = "linear",
    fixing_lag_bd: int = 1,
    principal_exchange: bool = False,
) -> dict:
    """平价利率:使合约 NPV=0 的固定利率(市场公允固定利率),与方向、名义无关。

    与估值同口径(曲线/利差/日期/本金交割/定盘滞后);利差抬高平价,
    本金交割不影响。方向与名义参数已省略(线性消去,不参与计算)。

    Args:
        与 value_swap 同名同义(除 fixed_rate/direction/notional 不参与外);
        curve 传空 = 自动加载行情曲线。

    Returns:
        {par_rate(%), annuity(N·Στ·df,固定腿单位利率现值,元), pv_floating(元)}。
        把 par_rate 代回 value_swap 的 fixed_rate 应得 NPV≈0。
    """
    return _post("/api/par_rate", _trade_args(
        benchmark, effective_date, maturity_date, valuation_date, 1.65,
        spread_bp, 100_000_000, "receiver", fixed_freq_months, curve,
        fixing_overrides, discount_basis, curve_interp, fixing_lag_bd,
        principal_exchange))


if __name__ == "__main__":
    mcp.run()  # stdio(缺省)
