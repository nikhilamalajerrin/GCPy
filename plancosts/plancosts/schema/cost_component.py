# plancosts/plancosts/schema/cost_component.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Any

HOURS_IN_MONTH = Decimal("730")


def _d(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _omit_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


# -----------------------------
# Go schema mirrors (1:1 fields)
# -----------------------------

@dataclass
class AttributeFilter:
    key: str
    value: Optional[str] = None
    value_regex: Optional[str] = None  # internal snake_case; converted in to_json

    def to_json(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"key": self.key}
        if self.value:
            out["value"] = self.value
        if self.value_regex:
            # keep underscore here; translators elsewhere can map to valueRegex if needed
            out["value_regex"] = self.value_regex
        return out


@dataclass
class ProductFilter:
    vendorName: Optional[str] = None
    service: Optional[str] = None
    productFamily: Optional[str] = None
    region: Optional[str] = None
    sku: Optional[str] = None
    attributeFilters: Optional[List[AttributeFilter]] = field(default=None)

    def to_json(self) -> Dict[str, Any]:
        return _omit_none({
            "vendorName": self.vendorName,
            "service": self.service,
            "productFamily": self.productFamily,
            "region": self.region,
            "sku": self.sku,
            "attributeFilters": (
                None if self.attributeFilters is None
                else [a.to_json() for a in self.attributeFilters if a and a.key]
            ),
        })


@dataclass
class PriceFilter:
    purchaseOption: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    descriptionRegex: Optional[str] = None
    termLength: Optional[str] = None
    termPurchaseOption: Optional[str] = None
    termOfferingClass: Optional[str] = None

    def to_json(self) -> Dict[str, Any]:
        return _omit_none(asdict(self))


# ---------------------------------------
# Schema CostComponent + runtime behavior
# ---------------------------------------

@dataclass
class CostComponent:
    # Schema fields (what to price)
    name: str
    unit: str
    hourlyQuantity: Optional[Decimal] = None
    monthlyQuantity: Optional[Decimal] = None
    productFilter: Optional[ProductFilter] = None
    priceFilter: Optional[PriceFilter] = None

    # Runtime fields (price + derived costs)
    _unit_price: Decimal = field(default=Decimal(0), init=False, repr=False)
    _price_hash: str = field(default="", init=False, repr=False)

    # ---- Go-like helpers (quantities) ----
    def HourlyQuantity(self) -> Decimal:
        if self.hourlyQuantity is not None:
            return _d(self.hourlyQuantity) or Decimal(0)
        if self.monthlyQuantity is not None:
            mq = _d(self.monthlyQuantity) or Decimal(0)
            return mq / HOURS_IN_MONTH
        return Decimal(0)

    def MonthlyQuantity(self) -> Decimal:
        if self.monthlyQuantity is not None:
            return _d(self.monthlyQuantity) or Decimal(0)
        if self.hourlyQuantity is not None:
            hq = _d(self.hourlyQuantity) or Decimal(0)
            return hq * HOURS_IN_MONTH
        return Decimal(0)

    # For renderers that show “Quantity” as monthly
    def Quantity(self) -> Decimal:
        return self.MonthlyQuantity()

    # ---- Runtime pricing API (Go parity) ----
    def SetPrice(self, unit_price: Any) -> None:
        self._unit_price = _d(unit_price) or Decimal(0)

    def Price(self) -> Decimal:
        return self._unit_price

    def SetPriceHash(self, h: str) -> None:
        self._price_hash = h or ""

    def price_hash(self) -> str:
        return self._price_hash

    def HourlyCost(self) -> Decimal:
        return self.Price() * self.HourlyQuantity()

    def MonthlyCost(self) -> Decimal:
        return self.Price() * self.MonthlyQuantity()

    def CalculateCosts(self) -> None:
        """
        No-op for API parity with Go. Our costs are computed on access.
        Calling this ensures callers that expect a method won't crash.
        """
        # Touch properties to mirror side effects in some call paths.
        _ = self.HourlyCost()
        _ = self.MonthlyCost()
        # Intentionally no caching here.

    # ---- JSON-ish dict for debugging/exports ----
    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "Name": self.name,
            "Unit": self.unit,
            "HourlyQuantity": str(self.HourlyQuantity()),
            "MonthlyQuantity": str(self.MonthlyQuantity()),
            "HourlyCost": str(self.HourlyCost()),
            "MonthlyCost": str(self.MonthlyCost()),
            "PriceHash": self.price_hash(),
        }
        if self.productFilter:
            out["ProductFilter"] = self.productFilter.to_json()
        if self.priceFilter:
            out["PriceFilter"] = self.priceFilter.to_json()
        return out
