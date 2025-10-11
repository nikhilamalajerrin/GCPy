# plancosts/resource/resource.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Callable, Optional

from plancosts.resource.filters import Filter  # simple key/value or regex filters

__all__ = [
    "PriceComponent",
    "Resource",
    "BasePriceComponent",
    "BaseResource",
    "flatten_sub_resources",
]

# ---- time unit seconds (Go: timeUnitSecs) ----
_TIME_UNIT_SECS: Dict[str, Decimal] = {
    "hour": Decimal(60 * 60),
    "month": Decimal(60 * 60 * 730),
}

def _round6(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# =========================
# Interfaces (Go-parity)
# =========================

class PriceComponent:
    # Required Go-style API
    def Name(self) -> str: ...
    def Unit(self) -> str: ...
    def Quantity(self) -> Decimal: ...
    def Price(self) -> Decimal: ...
    def SetPrice(self, price: Decimal) -> None: ...
    def HourlyCost(self) -> Decimal: ...

    # These two are used by the query layer
    def ProductFilter(self) -> Any: ...    # usually a dict (GraphQL filter) or None
    def PriceFilter(self) -> Any: ...      # usually a dict (GraphQL filter) or None

    # Python-friendly aliases
    def name(self) -> str: return self.Name()
    def unit(self) -> str: return self.Unit()
    def quantity(self) -> Decimal: return self.Quantity()
    def price(self) -> Decimal: return self.Price()
    def set_price(self, price: Decimal) -> None: self.SetPrice(price)
    def hourly_cost(self) -> Decimal: return self.HourlyCost()

    # Convenience (query layer calls these)
    def product_filter(self) -> Any: return self.ProductFilter()
    def price_filter(self) -> Any: return self.PriceFilter()


class Resource:
    # Required Go-style API
    def Address(self) -> str: ...
    def RawValues(self) -> Dict[str, Any]: ...
    def SubResources(self) -> List["Resource"]: ...
    def AddSubResource(self, sub: "Resource") -> None: ...
    def PriceComponents(self) -> List[PriceComponent]: ...
    def AddPriceComponent(self, pc: PriceComponent) -> None: ...
    def References(self) -> Dict[str, "Resource"] : ...
    def AddReference(self, name: str, res: "Resource") -> None: ...
    def ResourceCount(self) -> int: ...
    def SetResourceCount(self, count: int) -> None: ...
    def HasCost(self) -> bool: ...

    # Python-friendly aliases
    def address(self) -> str: return self.Address()
    def raw_values(self) -> Dict[str, Any]: return self.RawValues()
    def sub_resources(self) -> List["Resource"]: return self.SubResources()
    def add_sub_resource(self, sub: "Resource") -> None: self.AddSubResource(sub)
    def price_components(self) -> List[PriceComponent]: return self.PriceComponents()
    def add_price_component(self, pc: PriceComponent) -> None: self.AddPriceComponent(pc)
    def references(self) -> Dict[str, "Resource"]: return self.References()
    def add_reference(self, name: str, res: "Resource") -> None: self.AddReference(name, res)
    def resource_count(self) -> int: return self.ResourceCount()
    def has_cost(self) -> bool: return self.HasCost()


# =========================
# Implementations
# =========================

class BasePriceComponent(PriceComponent):
    """
    Mirrors Go's BasePriceComponent:
      - name, resource, unit, timeUnit
      - productFilter / priceFilter (dicts) for GraphQL layer
      - quantity multiplier func
      - price
    Quantity()   = 1 * quantityMultiplier * (month/timeUnit) * resourceCount  [rounded to 6 dp]
    HourlyCost() = Price() * Quantity() * (hour/month)
    """

    def __init__(self, name: str, resource: Resource, unit: str, time_unit: str):
        self._name = name
        self._resource = resource
        self._unit = unit
        self._time_unit = time_unit  # "hour" | "month"
        self._quantity_fn: Optional[Callable[[Resource], Decimal]] = None
        self._price: Decimal = Decimal(0)

        # IMPORTANT: keep these so GraphQLQueryRunner can call pc.product_filter()/price_filter()
        self._product_filter: Optional[Dict[str, Any]] = None
        self._price_filter: Optional[Dict[str, Any]] = None

    # -- Go API --
    def Name(self) -> str:
        return self._name

    def Unit(self) -> str:
        return self._unit

    def Quantity(self) -> Decimal:
        qty = Decimal(1)
        if self._quantity_fn is not None:
            try:
                qty *= Decimal(self._quantity_fn(self._resource))
            except Exception:
                pass

        month = _TIME_UNIT_SECS["month"]
        tu = _TIME_UNIT_SECS.get(self._time_unit, month)
        mul = month / tu if tu else Decimal(1)

        count = Decimal(self._resource.ResourceCount())
        return _round6(qty * mul * count)

    def SetQuantityMultiplierFunc(self, fn: Callable[[Resource], Decimal]) -> None:
        self._quantity_fn = fn

    def Price(self) -> Decimal:
        return self._price

    def SetPrice(self, price: Decimal) -> None:
        self._price = Decimal(price)

    def HourlyCost(self) -> Decimal:
        hour = _TIME_UNIT_SECS["hour"]
        month = _TIME_UNIT_SECS["month"]
        return self._price * self.Quantity() * (hour / month)

    # -- Filters for GraphQL --
    def ProductFilter(self) -> Any:
        # dict matching GraphQL ProductFilter (or None)
        return self._product_filter

    def PriceFilter(self) -> Any:
        # dict matching GraphQL PriceFilter (or None)
        return self._price_filter

    def SetProductFilter(self, pf: Optional[Dict[str, Any]]) -> None:
        self._product_filter = dict(pf) if isinstance(pf, dict) else None

    def SetPriceFilter(self, pf: Optional[Dict[str, Any]]) -> None:
        self._price_filter = dict(pf) if isinstance(pf, dict) else None

    # Python-friendly (query layer also calls these)
    def product_filter(self) -> Any:
        return self.ProductFilter()

    def price_filter(self) -> Any:
        return self.PriceFilter()


class BaseResource(Resource):
    """
    Mirrors Go's BaseResource.
    """

    def __init__(self, address: str, raw_values: Dict[str, Any], has_cost: bool):
        self._address = address
        self._raw_values = dict(raw_values or {})
        self._has_cost = bool(has_cost)
        self._references: Dict[str, Resource] = {}
        self._resource_count: int = 1
        self._sub_resources: List[Resource] = []
        self._price_components: List[PriceComponent] = []

    # -- Go API --
    def Address(self) -> str:
        return self._address

    def RawValues(self) -> Dict[str, Any]:
        return self._raw_values

    def SubResources(self) -> List[Resource]:
        return sorted(self._sub_resources, key=lambda r: r.Address())

    def AddSubResource(self, sub: Resource) -> None:
        self._sub_resources.append(sub)

    def PriceComponents(self) -> List[PriceComponent]:
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
        # Propagate like Go does
        for sub in self._sub_resources:
            try:
                sub.SetResourceCount(count)
            except Exception:
                pass

    def HasCost(self) -> bool:
        return self._has_cost


# =========================
# Helpers
# =========================

def flatten_sub_resources(resource: Resource) -> List[Resource]:
    out: List[Resource] = []
    for sub in resource.SubResources():
        out.append(sub)
        if sub.SubResources():
            out.extend(flatten_sub_resources(sub))
    return out
