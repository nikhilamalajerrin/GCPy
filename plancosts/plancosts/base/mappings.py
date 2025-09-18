"""
Mappings between Terraform resources and pricing components.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any, TYPE_CHECKING
from decimal import Decimal
from .filters import Filter, merge_filters

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
    """
    Includes:
      - default/value-derived filters
      - optional override filters based on the *resource*
      - optional custom cost based on price + resource
    """
    def __init__(
        self,
        time_unit: str = "hour",
        default_filters: Optional[List[Filter]] = None,
        value_mappings: Optional[List[ValueMapping]] = None,
        should_skip: Optional[Callable[[Dict[str, Any]], bool]] = None,
        calculate_cost: Optional[Callable[[Decimal, "Resource"], Decimal]] = None,
        override_filters: Optional[Callable[["Resource"], List[Filter]]] = None,
    ):
        self.time_unit = time_unit
        self.default_filters = default_filters or []
        self.value_mappings = value_mappings or []
        self.should_skip = should_skip
        self.calculate_cost = calculate_cost
        self.override_filters = override_filters

    def get_filters(self, resource: "Resource") -> List[Filter]:
        """
        Merge default + value-derived + override filters.
        """
        values = resource.raw_values()
        value_filters = self._value_filters(resource)
        override = self.override_filters(resource) if self.override_filters else []
        return merge_filters(self.default_filters, value_filters, override)

    def _value_filters(self, resource: "Resource") -> List[Filter]:
        mapped: List[Filter] = []
        values = resource.raw_values()
        for from_key, from_val in values.items():
            vm_match: Optional[ValueMapping] = None
            for vm in self.value_mappings:
                if vm.from_key == from_key:
                    vm_match = vm
                    break
            if not vm_match:
                continue
            to_val = vm_match.mapped_value(from_val)
            if to_val:
                mapped.append(Filter(key=vm_match.to_key, value=to_val))
        return mapped


class ResourceMapping:
    """
    Adds:
      - override_sub_resource_raw_values(resource) -> inject/replace subresource raw values
      - adjust_cost(resource, cost) -> modify hourly cost (e.g., multiply by count)
      - non_costable -> skip entirely in costing
    """
    def __init__(
        self,
        price_mappings: Optional[Dict[str, PriceMapping]] = None,
        sub_resource_mappings: Optional[Dict[str, "ResourceMapping"]] = None,
        override_sub_resource_raw_values: Optional[Callable[["Resource"], Dict[str, List[dict]]]] = None,
        adjust_cost: Optional[Callable[["Resource", Decimal], Decimal]] = None,
        non_costable: bool = False,
    ):
        self.price_mappings = price_mappings or {}
        self.sub_resource_mappings = sub_resource_mappings or {}
        self.override_sub_resource_raw_values = override_sub_resource_raw_values
        self.adjust_cost = adjust_cost
        self.non_costable = non_costable
