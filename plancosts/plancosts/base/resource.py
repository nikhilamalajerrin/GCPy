"""
Resource abstraction for cloud resources.
"""
from __future__ import annotations

from typing import Dict, List, Any
from abc import ABC, abstractmethod
from decimal import Decimal

from .filters import Filter
from .mappings import ResourceMapping


class Resource(ABC):
    @abstractmethod
    def address(self) -> str: ...
    @abstractmethod
    def raw_values(self) -> Dict[str, Any]: ...
    @abstractmethod
    def references(self) -> Dict[str, "Resource"]: ...
    @abstractmethod
    def get_filters(self) -> List[Filter]: ...
    @abstractmethod
    def add_reference(self, name: str, reference: "Resource"): ...
    @abstractmethod
    def add_sub_resources(self) -> None: ...
    @abstractmethod
    def sub_resources(self) -> List["Resource"]: ...
    @abstractmethod
    def price_components(self) -> List: ...
    @abstractmethod
    def adjust_cost(self, cost: Decimal) -> Decimal: ...
    @abstractmethod
    def non_costable(self) -> bool: ...


class BaseResource(Resource):
    def __init__(self, address: str, raw_values: Dict[str, Any], resource_mapping: ResourceMapping, provider_filters: List[Filter]):
        self._address = address
        self._raw_values = raw_values or {}
        self._resource_mapping = resource_mapping
        self._references: Dict[str, Resource] = {}
        self._provider_filters = provider_filters
        self._price_components: List = []
        self._sub_resources: List[Resource] = []

        self._initialize_price_components()
        # NOTE: subresources are built *after* references are added via add_sub_resources()

    def _initialize_price_components(self) -> None:
        from .pricecomponent import BasePriceComponent
        for name, price_mapping in (self._resource_mapping.price_mappings or {}).items():
            self._price_components.append(BasePriceComponent(name, self, price_mapping))

    # ----------------------------
    # Resource interface
    # ----------------------------
    def address(self) -> str: return self._address
    def raw_values(self) -> Dict[str, Any]: return self._raw_values
    def references(self) -> Dict[str, "Resource"]: return self._references
    def get_filters(self) -> List[Filter]: return self._provider_filters
    def add_reference(self, name: str, reference: "Resource"): self._references[name] = reference

    def add_sub_resources(self) -> None:
        """
        Build subresources using:
          - override_sub_resource_raw_values(resource) if provided
          - else fall back to this resource's raw_values()
        Address pattern mirrors Go: "<parent>.<name>[<i>]".
        """
        sub_map = getattr(self._resource_mapping, "sub_resource_mappings", {}) or {}
        override_fn = getattr(self._resource_mapping, "override_sub_resource_raw_values", None)

        sub_resources: List[Resource] = []
        overridden: Dict[str, List[dict]] = override_fn(self) if override_fn else {}

        for name, sub_mapping in sub_map.items():
            # Prefer overridden raw values if provided
            group_raw = overridden.get(name)

            if group_raw is None:
                # fallback to the resource raw values
                val = self._raw_values.get(name)
                if val is None:
                    items: List[dict] = []
                elif isinstance(val, list):
                    items = [rv for rv in val if isinstance(rv, dict)]
                elif isinstance(val, dict):
                    items = [val]
                else:
                    items = []
            else:
                items = [rv for rv in group_raw if isinstance(rv, dict)]

            for i, s_raw in enumerate(items):
                sub_address = f"{self._address}.{name}[{i}]"
                sub_resources.append(
                    BaseResource(
                        address=sub_address,
                        raw_values=s_raw,
                        resource_mapping=sub_mapping,
                        provider_filters=self._provider_filters,
                    )
                )
        self._sub_resources = sub_resources

    def sub_resources(self) -> List["Resource"]: return self._sub_resources
    def price_components(self) -> List: return self._price_components

    def adjust_cost(self, cost: Decimal) -> Decimal:
        fn = getattr(self._resource_mapping, "adjust_cost", None)
        return fn(self, cost) if fn else cost

    def non_costable(self) -> bool:
        return bool(getattr(self._resource_mapping, "non_costable", False))
