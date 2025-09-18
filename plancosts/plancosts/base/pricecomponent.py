"""
Price component abstraction for cost calculations.
"""
from __future__ import annotations

from typing import List
from decimal import Decimal, InvalidOperation
from abc import ABC, abstractmethod

from .filters import Filter, merge_filters
from .mappings import PriceMapping


class PriceComponent(ABC):
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def should_skip(self) -> bool: ...
    @abstractmethod
    def get_filters(self) -> List[Filter]: ...
    @abstractmethod
    def calculate_hourly_cost(self, price: Decimal) -> Decimal: ...


class BasePriceComponent(PriceComponent):
    def __init__(self, name: str, resource, price_mapping: PriceMapping):
        self._name = name
        self._resource = resource
        self._price_mapping = price_mapping

    def name(self) -> str:
        return self._name

    def should_skip(self) -> bool:
        if getattr(self._price_mapping, "should_skip", None):
            return bool(self._price_mapping.should_skip(self._resource.raw_values()))
        return False

    def get_filters(self) -> List[Filter]:
        # CHANGED: mapping.get_filters now receives the Resource
        mapping_filters = self._price_mapping.get_filters(self._resource)
        return merge_filters(self._resource.get_filters(), mapping_filters)

    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        # Custom cost transform (price, resource)
        if getattr(self._price_mapping, "calculate_cost", None):
            cost = self._price_mapping.calculate_cost(price, self._resource)
        else:
            cost = price

        time_unit_seconds = {"hour": 3600, "month": 3600 * 730}
        unit = getattr(self._price_mapping, "time_unit", "hour") or "hour"
        denom = time_unit_seconds.get(unit)
        if not denom:
            hourly = cost
        else:
            try:
                hourly = cost * (Decimal(time_unit_seconds["hour"]) / Decimal(denom))
            except (InvalidOperation, ZeroDivisionError):
                hourly = cost

        # NEW: let resource adjust final hourly cost (e.g., multiply by ASG desired capacity)
        hourly = self._resource.adjust_cost(hourly)
        return hourly
