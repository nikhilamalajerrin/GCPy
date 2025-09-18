"""
Resource abstraction for cloud resources.
"""
from __future__ import annotations

from typing import Dict, List, Any
from abc import ABC, abstractmethod

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
    def add_reference(self, address: str, reference: "Resource"): ...
    @abstractmethod
    def sub_resources(self) -> List["Resource"]: ...
    @abstractmethod
    def price_components(self) -> List: ...


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
        self._initialize_sub_resources()

    def _initialize_price_components(self) -> None:
        from .pricecomponent import BasePriceComponent
        for name, price_mapping in (self._resource_mapping.price_mappings or {}).items():
            self._price_components.append(BasePriceComponent(name, self, price_mapping))

    def _initialize_sub_resources(self) -> None:
        sub_map = getattr(self._resource_mapping, "sub_resource_mappings", {}) or {}
        for name, sub_mapping in sub_map.items():
            group_raw = self._raw_values.get(name)
            if group_raw is None:
                items: List[Dict[str, Any]] = []
            elif isinstance(group_raw, list):
                items = [rv for rv in group_raw if isinstance(rv, dict)]
            elif isinstance(group_raw, dict):
                items = [group_raw]
            else:
                items = []
            for i, s_raw in enumerate(items):
                sub_address = f"{self._address}.{name}.{i}"
                self._sub_resources.append(
                    BaseResource(sub_address, s_raw, sub_mapping, self._provider_filters)
                )

    def address(self) -> str: return self._address
    def raw_values(self) -> Dict[str, Any]: return self._raw_values
    def references(self) -> Dict[str, "Resource"]: return self._references
    def get_filters(self) -> List[Filter]: return self._provider_filters
    def add_reference(self, address: str, reference: "Resource"): self._references[address] = reference
    def sub_resources(self) -> List["Resource"]: return self._sub_resources
    def price_components(self) -> List: return self._price_components
