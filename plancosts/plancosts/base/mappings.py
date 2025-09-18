"""
Mappings between Terraform resources and pricing components.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any, TYPE_CHECKING
from decimal import Decimal
from .filters import Filter, merge_filters

# Avoid runtime import cycle: only import Resource for type-checkers
if TYPE_CHECKING:
    from .resource import Resource


class ValueMapping:
    def __init__(self, from_key: str, to_key: str, to_value_fn: Optional[Callable[[Any], str]] = None):
        self.from_key = from_key
        self.to_key = to_key
        self.to_value_fn = to_value_fn

    def mapped_value(self, from_val: Any) -> str:
        if self.to_value_fn:
            return self.to_value_fn(from_val)
        return str(from_val) if from_val is not None else ""


class PriceMapping:
    def __init__(
        self,
        time_unit: str = "hour",
        default_filters: Optional[List[Filter]] = None,
        value_mappings: Optional[List[ValueMapping]] = None,
        should_skip: Optional[Callable[[Dict[str, Any]], bool]] = None,
        # type-only forward ref to avoid import cycle
        calculate_cost: Optional[Callable[[Decimal, "Resource"], Decimal]] = None,
    ):
        self.time_unit = time_unit
        self.default_filters = default_filters or []
        self.value_mappings = value_mappings or []
        self.should_skip = should_skip
        self.calculate_cost = calculate_cost

    def get_filters(self, values: Dict[str, Any]) -> List[Filter]:
        return merge_filters(self.default_filters, self._value_filters(values))

    def _value_filters(self, values: Dict[str, Any]) -> List[Filter]:
        mapped: List[Filter] = []
        for vm in self.value_mappings:
            if vm.from_key in values:
                to_val = vm.mapped_value(values[vm.from_key])
                if to_val:
                    mapped.append(Filter(key=vm.to_key, value=to_val))
        return mapped


class ResourceMapping:
    def __init__(
        self,
        price_mappings: Optional[Dict[str, PriceMapping]] = None,
        sub_resource_mappings: Optional[Dict[str, "ResourceMapping"]] = None,
    ):
        self.price_mappings = price_mappings or {}
        self.sub_resource_mappings = sub_resource_mappings or {}
