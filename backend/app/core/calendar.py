"""交易日历:数据范围内以 FR007 定盘日期为真实交易日;范围外回退周末规则。"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


class Calendar:
    def __init__(self, business_days: Iterable[date]):
        days = set(business_days)
        self._bd = days
        self.min_date = min(days)
        self.max_date = max(days)

    def uses_fallback(self, d: date) -> bool:
        """d 是否落在数据覆盖范围之外(该区域日历为周末近似)。"""
        return d < self.min_date or d > self.max_date

    def is_business_day(self, d: date) -> bool:
        if self.uses_fallback(d):
            return d.weekday() < 5
        return d in self._bd

    def next_business_day(self, d: date) -> date:
        nd = d + timedelta(days=1)
        while not self.is_business_day(nd):
            nd += timedelta(days=1)
        return nd

    def prev_business_day(self, d: date) -> date:
        pd = d - timedelta(days=1)
        while not self.is_business_day(pd):
            pd -= timedelta(days=1)
        return pd

    def adjust_modified_following(self, d: date) -> date:
        """修正顺延:下一交易日;若跨月则改为前一交易日。"""
        if self.is_business_day(d):
            return d
        nd = self.next_business_day(d)
        if nd.month != d.month:
            return self.prev_business_day(d)
        return nd
