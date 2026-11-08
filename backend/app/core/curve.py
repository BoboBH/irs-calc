"""互换零息曲线:零利率插值方法可选,平推外推,贴现口径可选。

- interp="linear"(默认):报价点之间零利率线性插值 —— 厂商逐分位对齐口径
- interp="hermite":单调三次 Hermite(Fritsch–Carlson),节点切线连续、无过冲,
  端点切线取 0 与平推衔接;贴现与浮动端重置利率预测(远期)都随之变化

- discount_basis="simple"(默认):DF = 1/(1+y·τ),白皮书口径
- discount_basis="cont":DF = exp(−y·τ),连续复利(与外部厂商系统对账用)

扰动方式(供 DV01):
- shifted_parallel: 全部期限点零利率 +bump
- shifted_keys: 各关键期限点 +bump_k,相邻关键期限之间的点按 τ 线性(三角形)分摊,
  两端外侧取最近关键期限的 bump。平行移动 = 所有 bump_k 相等。
扰动曲线继承原曲线的插值方法与贴现口径。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Sequence

DAY_COUNT = 365
DISCOUNT_BASES = ("simple", "cont")
INTERP_METHODS = ("linear", "hermite")


@dataclass(frozen=True)
class CurvePoint:
    label: str
    date: date
    rate: float  # 小数,如 0.014 = 1.4%


class ZeroCurve:
    def __init__(self, valuation_date: date, points: Sequence[CurvePoint],
                 discount_basis: str = "simple", interp: str = "linear"):
        if discount_basis not in DISCOUNT_BASES:
            raise ValueError(f"贴现口径须为 {DISCOUNT_BASES},得到: {discount_basis!r}")
        if interp not in INTERP_METHODS:
            raise ValueError(f"插值方法须为 {INTERP_METHODS},得到: {interp!r}")
        pts = sorted(points, key=lambda p: p.date)
        if len(pts) < 1:
            raise ValueError("曲线至少需要一个期限点")
        if pts[0].date < valuation_date:
            raise ValueError("期限点日期不能早于估值日")
        for a, b in zip(pts, pts[1:]):
            if a.date == b.date:
                raise ValueError(f"期限点日期重复: {b.date}")
        self.valuation_date = valuation_date
        self.points = pts
        self.discount_basis = discount_basis
        self.interp = interp
        self._taus = [(p.date - valuation_date).days / DAY_COUNT for p in pts]
        self._rates = [p.rate for p in pts]
        self._tans = (self._hermite_tangents(self._taus, self._rates)
                      if interp == "hermite" else None)

    @staticmethod
    def _hermite_tangents(taus: Sequence[float], rates: Sequence[float]) -> list[float]:
        """Fritsch–Carlson 单调三次切线(与前端显示层同法):
        区间割率为 del;内部点两侧割率变号(局部极值)时切线取 0 防过冲,
        否则取加权调和平均 w1=2h1+h0, w2=h1+2h0;端点切线 0,与两端平推衔接。"""
        n = len(taus)
        tan = [0.0] * n
        dels = [(rates[i + 1] - rates[i]) / (taus[i + 1] - taus[i]) for i in range(n - 1)]
        for i in range(1, n - 1):
            d0, d1 = dels[i - 1], dels[i]
            if d0 * d1 <= 0:
                continue
            h0 = taus[i] - taus[i - 1]
            h1 = taus[i + 1] - taus[i]
            w1 = 2 * h1 + h0
            w2 = h1 + 2 * h0
            tan[i] = (w1 + w2) / (w1 / d0 + w2 / d1)
        return tan

    # ---- 内部 ----
    def _tau(self, d: date) -> float:
        return (d - self.valuation_date).days / DAY_COUNT

    @staticmethod
    def _interp_bump(taus: Sequence[float], bumps: Sequence[float], tau: float) -> float:
        """关键期限 bump 按 τ 线性分摊;两端外平推。"""
        if tau <= taus[0]:
            return bumps[0]
        if tau >= taus[-1]:
            return bumps[-1]
        for i in range(len(taus) - 1):
            if taus[i] <= tau <= taus[i + 1]:
                w = (tau - taus[i]) / (taus[i + 1] - taus[i])
                return bumps[i] + (bumps[i + 1] - bumps[i]) * w
        raise AssertionError

    def _shifted(self, key_dates: Sequence[date], bumps: Sequence[float]) -> "ZeroCurve":
        key_taus = [(kd - self.valuation_date).days / DAY_COUNT for kd in key_dates]
        new_points = []
        for p in self.points:
            tau = self._tau(p.date)
            b = self._interp_bump(key_taus, bumps, tau)
            new_points.append(CurvePoint(p.label, p.date, p.rate + b))
        return ZeroCurve(self.valuation_date, new_points, self.discount_basis, self.interp)

    # ---- 公开 ----
    @property
    def labels(self) -> list[str]:
        return [p.label for p in self.points]

    @property
    def point_dates(self) -> list[date]:
        return [p.date for p in self.points]

    def shifted_parallel(self, bump: float) -> "ZeroCurve":
        return self._shifted(self.point_dates, [bump] * len(self.points))

    def shifted_keys(self, key_dates: Sequence[date], bumps: Sequence[float]) -> "ZeroCurve":
        if len(key_dates) != len(bumps):
            raise ValueError("key_dates 与 bumps 长度不一致")
        key_taus = [(kd - self.valuation_date).days / DAY_COUNT for kd in key_dates]
        if any(a >= b for a, b in zip(key_taus, key_taus[1:])):
            raise ValueError("key_dates 必须严格递增(按估值日起的 τ)")
        return self._shifted(key_dates, bumps)

    def zero_rate(self, d: date) -> float:
        tau = self._tau(d)
        if tau <= 0:
            return self.points[0].rate
        taus, rates = self._taus, self._rates
        if tau >= taus[-1]:
            return rates[-1]
        if tau <= taus[0]:
            return rates[0]
        for i in range(len(taus) - 1):
            if taus[i] <= tau <= taus[i + 1]:
                if self.interp == "hermite":
                    h = taus[i + 1] - taus[i]
                    t = (tau - taus[i]) / h
                    t2, t3 = t * t, t * t * t
                    m0, m1 = self._tans[i], self._tans[i + 1]
                    return ((2 * t3 - 3 * t2 + 1) * rates[i]
                            + (t3 - 2 * t2 + t) * h * m0
                            + (-2 * t3 + 3 * t2) * rates[i + 1]
                            + (t3 - t2) * h * m1)
                w = (tau - taus[i]) / (taus[i + 1] - taus[i])
                return rates[i] + (rates[i + 1] - rates[i]) * w
        raise AssertionError

    def df(self, d: date) -> float:
        tau = self._tau(d)
        if tau == 0:
            return 1.0
        y = self.zero_rate(d)
        # τ<0(锚定日之前)按同式反推(DF>1):静态归因曲线(锚 t1)需对重置日
        # < t1 的子区间算远期;钳制会系统性压低远期、虚增残差。zero_rate 的 τ≤0
        # 平推保持不变,反推正好取首点利率。
        if self.discount_basis == "cont":
            return math.exp(-y * tau)
        return 1.0 / (1.0 + y * tau)

    def forward(self, d1: date, d2: date, day_count: int = DAY_COUNT) -> float:
        if d2 <= d1:
            raise ValueError("forward 需要 d2 > d1")
        tau = (d2 - d1).days / day_count
        return (self.df(d1) / self.df(d2) - 1.0) / tau
