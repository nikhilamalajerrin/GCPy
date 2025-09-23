# plancosts/resource/resource.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Callable, Optional

from plancosts.resource.filters import Filter  # reuse shared Filter type

__all__ = [
    "PriceComponent",
    "Resource",
    "BasePriceComponent",
    "BaseResource",
    "flatten_sub_resources",
]

# ----------------------------
# Constants (Go: timeUnitSecs)
# ----------------------------

_TIME_UNIT_SECS: Dict[str, Decimal] = {
    "hour": Decimal(60 * 60),
    "month": Decimal(60 * 60 * 730),
}

# ----------------------------
# Interfaces (Go parity)
# ----------------------------


class PriceComponent:
    """Go-like interface for price components."""

    # --- required API (Go names) ---
    def Name(self) -> str: ...
    def Unit(self) -> str: ...
    def Filters(self) -> List[Filter]: ...
    def Quantity(self) -> Decimal: ...
    def Price(self) -> Decimal: ...
    def SetPrice(self, price: Decimal) -> None: ...
    def HourlyCost(self) -> Decimal: ...

    # --- python-friendly aliases ---
    def name(self) -> str:
        return self.Name()

    def unit(self) -> str:
        return self.Unit()

    def filters(self) -> List[Filter]:
        return self.Filters()

    def quantity(self) -> Decimal:
        return self.Quantity()

    def price(self) -> Decimal:
        return self.Price()

    def set_price(self, price: Decimal) -> None:
        self.SetPrice(price)

    def hourly_cost(self) -> Decimal:
        return self.HourlyCost()


class Resource:
    """Go-like interface for resources."""

    # --- required API (Go names) ---
    def Address(self) -> str: ...
    def RawValues(self) -> Dict[str, Any]: ...
    def SubResources(self) -> List["Resource"]: ...
    def AddSubResource(self, sub: "Resource") -> None: ...
    def PriceComponents(self) -> List[PriceComponent]: ...
    def AddPriceComponent(self, pc: PriceComponent) -> None: ...
    def References(self) -> Dict[str, "Resource"]: ...
    def AddReference(self, name: str, res: "Resource") -> None: ...
    def ResourceCount(self) -> int: ...
    def SetResourceCount(self, count: int) -> None: ...
    def HasCost(self) -> bool: ...

    # --- python-friendly aliases ---
    def address(self) -> str:
        return self.Address()

    def raw_values(self) -> Dict[str, Any]:
        return self.RawValues()

    def sub_resources(self) -> List["Resource"]:
        return self.SubResources()

    def add_sub_resource(self, sub: "Resource") -> None:
        self.AddSubResource(sub)

    def price_components(self) -> List[PriceComponent]:
        return self.PriceComponents()

    def add_price_component(self, pc: PriceComponent) -> None:
        self.AddPriceComponent(pc)

    def references(self) -> Dict[str, "Resource"]:
        return self.References()

    def add_reference(self, name: str, res: "Resource") -> None:
        self.AddReference(name, res)

    def resource_count(self) -> int:
        return self.ResourceCount()

    def set_resource_count(self, count: int) -> None:
        self.SetResourceCount(count)

    def has_cost(self) -> bool:
        return self.HasCost()


# ----------------------------
# Base implementations (Go parity)
# ----------------------------


class BasePriceComponent(PriceComponent):
    """
    Mirrors Go's BasePriceComponent:
    - name, resource, unit, timeUnit, filters
    - quantityMultiplierFunc
    - price
    Quantity() = 1 * quantityMultiplier * (month/timeUnit) * resourceCount
    HourlyCost() = Price() * Quantity() * (hour/month)
    """

    def __init__(
        self,
        name: str,
        resource: Resource,
        unit: str,
        time_unit: str,
    ):
        self._name = name
        self._resource = resource
        self._unit = unit
        self._time_unit = time_unit  # "hour" | "month"
        self._filters: List[Filter] = []
        self._price: Decimal = Decimal(0)
        self._quantity_fn: Optional[Callable[[Resource], Decimal]] = None

    # --- Go API ---
    def Name(self) -> str:
        return self._name

    def Unit(self) -> str:
        return self._unit

    def Filters(self) -> List[Filter]:
        return list(self._filters)

    def AddFilters(self, filters: List[Filter]) -> None:
        self._filters.extend(filters)

    def Quantity(self) -> Decimal:
        qty = Decimal(1)
        if self._quantity_fn is not None:
            try:
                qty *= self._quantity_fn(self._resource)
            except Exception:
                # stay conservative; same behavior as Go (no panic)
                pass

        # month/timeUnit multiplier
        month = _TIME_UNIT_SECS["month"]
        tu = _TIME_UNIT_SECS.get(self._time_unit, month)
        time_unit_multiplier = month / tu if tu else Decimal(1)

        # resource count
        count = Decimal(self._resource.ResourceCount())

        return qty * time_unit_multiplier * count

    def SetQuantityMultiplierFunc(self, fn: Callable[[Resource], Decimal]) -> None:
        self._quantity_fn = fn

    def Price(self) -> Decimal:
        return self._price

    def SetPrice(self, price: Decimal) -> None:
        self._price = Decimal(price)

    def HourlyCost(self) -> Decimal:
        # month -> hour conversion
        hour = _TIME_UNIT_SECS["hour"]
        month = _TIME_UNIT_SECS["month"]
        month_to_hour = hour / month
        return self._price * self.Quantity() * month_to_hour

    # --- python-friendly adders ---
    def add_filters(self, filters: List[Filter]) -> None:
        self.AddFilters(filters)


class BaseResource(Resource):
    """
    Mirrors Go's BaseResource:
    - address, rawValues, hasCost, references, resourceCount
    - subResources[], priceComponents[]
    """

    def __init__(self, address: str, raw_values: Dict[str, Any], has_cost: bool):
        self._address = address
        self._raw_values = raw_values or {}
        self._has_cost = has_cost
        self._references: Dict[str, Resource] = {}
        self._resource_count: int = 1
        self._sub_resources: List[Resource] = []
        self._price_components: List[PriceComponent] = []

    # --- Go API ---
    def Address(self) -> str:
        return self._address

    def RawValues(self) -> Dict[str, Any]:
        return self._raw_values

    def SubResources(self) -> List[Resource]:
        # Go sorts by Address(); keep stable order here
        return sorted(self._sub_resources, key=lambda r: r.Address())

    def AddSubResource(self, sub: Resource) -> None:
        self._sub_resources.append(sub)

    def PriceComponents(self) -> List[PriceComponent]:
        # Go sorts by Name()
        return sorted(self._price_components, key=lambda pc: pc.Name())

    def AddPriceComponent(self, pc: PriceComponent) -> None:
        self._price_components.append(pc)

    def References(self) -> Dict[str, Resource]:
        return self._references

    def AddReference(self, name: str, res: Resource) -> None:
        self._references[name] = res

    def ResourceCount(self) -> int:
        return self._resource_count

    def SetResourceCount(self, count: int) -> None:
        self._resource_count = int(count)

    def HasCost(self) -> bool:
        return self._has_cost


# ----------------------------
# Helpers
# ----------------------------


def flatten_sub_resources(resource: Resource) -> List[Resource]:
    """Equivalent to Go FlattenSubResources."""
    out: List[Resource] = []
    for sub in resource.SubResources():
        out.append(sub)
        if sub.SubResources():
            out.extend(flatten_sub_resources(sub))
    return out
