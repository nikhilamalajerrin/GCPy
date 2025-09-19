"""
Resource & PriceComponent abstractions (refactored model).
"""
from __future__ import annotations
from typing import Dict, List, Any
from abc import ABC, abstractmethod
from decimal import Decimal


class PriceComponent(ABC):
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def resource(self) -> "Resource": ...
    @abstractmethod
    def filters(self) -> List["Filter"]: ...
    @abstractmethod
    def set_price(self, price: Decimal) -> None: ...
    @abstractmethod
    def hourly_cost(self) -> Decimal: ...
    


class Resource(ABC):
    @abstractmethod
    def address(self) -> str: ...
    @abstractmethod
    def raw_values(self) -> Dict[str, Any]: ...
    @abstractmethod
    def references(self) -> Dict[str, "Resource"]: ...
    @abstractmethod
    def add_reference(self, name: str, resource: "Resource") -> None: ...
    @abstractmethod
    def sub_resources(self) -> List["Resource"]: ...
    @abstractmethod
    def price_components(self) -> List[PriceComponent]: ...
    @abstractmethod
    def has_cost(self) -> bool: ...


# Utility (used by snapshots)
def get_price_component(resource: Resource, name: str) -> PriceComponent | None:
    for pc in resource.price_components():
        if pc.name() == name:
            return pc
    return None
