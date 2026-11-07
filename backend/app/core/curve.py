"""互换零息曲线:单利贴现 DF=1/(1+y·τ),零利率线性插值,平推外推。

扰动方式(供 DV01):
- shifted_parallel: 全部期限点零利率 +bump
- shifted_keys: 各关键期限点 +bump_k,相邻关键期限之间的点按 τ 线性(三角形)分摊,
  两端外侧取最近关键期限的 bump。平行移动 = 所有 bump_k 相等。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

DAY_COUNT = 365


@dataclass(frozen=True)
class CurvePoint:
    label: str
    date: date
    rate: float  # 小数,如 0.014 = 1.4%


class ZeroCurve:
    def __init__(self, valuation_date: date, points: Sequence[CurvePoint]):
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
        return ZeroCurve(self.valuation_date, new_points)

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
        taus = [self._tau(p.date) for p in self.points]
        rates = [p.rate for p in self.points]
        if tau >= taus[-1]:
            return rates[-1]
        if tau <= taus[0]:
            return rates[0]
        for i in range(len(taus) - 1):
            if taus[i] <= tau <= taus[i + 1]:
                w = (tau - taus[i]) / (taus[i + 1] - taus[i])
                return rates[i] + (rates[i + 1] - rates[i]) * w
        raise AssertionError

    def df(self, d: date) -> float:
        tau = self._tau(d)
        if tau == 0:
            return 1.0
        # τ<0(锚定日之前)按同式反推(DF>1):静态归因曲线(锚 t1)需对重置日
        # < t1 的子区间算远期;钳制会系统性压低远期、虚增残差。zero_rate 的 τ≤0
        # 平推保持不变,反推正好取首点利率。
        return 1.0 / (1.0 + self.zero_rate(d) * tau)

    def forward(self, d1: date, d2: date, day_count: int = DAY_COUNT) -> float:
        if d2 <= d1:
            raise ValueError("forward 需要 d2 > d1")
        tau = (d2 - d1).days / day_count
        return (self.df(d1) / self.df(d2) - 1.0) / tau
