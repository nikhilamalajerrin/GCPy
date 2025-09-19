from __future__ import annotations
from decimal import Decimal
from typing import List, Dict, Any, Optional


class PriceComponentMock:
    """
    Minimal test double:
    - hourly_cost() returns a fixed hourly cost
    - set_price() stores the fetched unit price
    - filters() returns [] unless set
    """
    def __init__(self, hourly_cost: Decimal, name: str = ""):
        self._name = name
        self._hourly_cost = Decimal(hourly_cost)
        self._price: Optional[Decimal] = None
        self._filters: List[Dict[str, Any]] = []

    def name(self) -> str:
        return self._name

    def filters(self) -> List[Dict[str, Any]]:
        return self._filters

    def set_price(self, price: Decimal) -> None:
        self._price = Decimal(price)

    def hourly_cost(self) -> Decimal:
        return self._hourly_cost

    # Helper for tests
    @property
    def price(self) -> Optional[Decimal]:
        return self._price


class ResourceMock:
    def __init__(
        self,
        addr: str,
        pcs: List[PriceComponentMock] | None = None,
        subs: List["ResourceMock"] | None = None,
    ):
        self._addr = addr
        self._pcs = list(pcs or [])
        self._subs = list(subs or [])
        self._refs: Dict[str, "ResourceMock"] = {}

    def address(self) -> str:
        return self._addr

    def price_components(self) -> List[PriceComponentMock]:
        return self._pcs

    def sub_resources(self) -> List["ResourceMock"]:
        return self._subs

    def references(self) -> Dict[str, "ResourceMock"]:
        return self._refs

    def add_reference(self, name: str, res: "ResourceMock") -> None:
        self._refs[name] = res

    def has_cost(self) -> bool:
        return True

    def raw_values(self) -> Dict[str, Any]:
        return {}
