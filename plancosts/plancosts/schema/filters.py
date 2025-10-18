# plancosts/schema/filters.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


__all__ = [
    "AttributeFilter",
    "ProductFilter",
    "PriceFilter",
]


def _omit_none(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of d without None values."""
    return {k: v for k, v in d.items() if v is not None}


def _omit_none_and_empty(d: Dict[str, Any]) -> Dict[str, Any]:
    """Like _omit_none, but also drops empty strings and empty lists/dicts."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if v == "" or v == [] or v == {}:
            continue
        out[k] = v
    return out


# -----------------------------------------------------------------------------
# AttributeFilter  (Go: key + value | value_regex)
# GraphQL keys: "key", "value", "value_regex"
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AttributeFilter:
    key: str
    value: Optional[str] = None
    value_regex: Optional[str] = None

    def __post_init__(self) -> None:
        # Enforce XOR: allow exactly one of value / value_regex (or relax to "at least one").
        if (self.value is None) == (self.value_regex is None):
            # both None or both set -> invalid
            raise ValueError(
                "AttributeFilter requires exactly one of {value, value_regex} to be set."
            )

    @staticmethod
    def value_eq(key: str, val: str) -> "AttributeFilter":
        return AttributeFilter(key=key, value=val)

    @staticmethod
    def regex(key: str, pattern: str) -> "AttributeFilter":
        return AttributeFilter(key=key, value_regex=pattern)

    def to_dict(self) -> Dict[str, Any]:
        return _omit_none({
            "key": self.key,
            "value": self.value,
            "value_regex": self.value_regex,
        })


# -----------------------------------------------------------------------------
# ProductFilter
# GraphQL keys: vendorName, service, productFamily, region, sku, attributeFilters[]
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProductFilter:
    vendorName: Optional[str] = None
    service: Optional[str] = None
    productFamily: Optional[str] = None
    region: Optional[str] = None
    sku: Optional[str] = None
    # Keep None to completely omit the key when you don't want to send it:
    attributeFilters: Optional[List[AttributeFilter]] = field(default=None)

    # If you prefer always sending an empty list instead of omitting the key,
    # switch to: attributeFilters: List[AttributeFilter] = field(default_factory=list)

    def to_dict(self, omit_empty: bool = False) -> Dict[str, Any]:
        d = {
            "vendorName": self.vendorName,
            "service": self.service,
            "productFamily": self.productFamily,
            "region": self.region,
            "sku": self.sku,
            "attributeFilters": (
                None
                if self.attributeFilters is None
                else [a.to_dict() for a in self.attributeFilters]
            ),
        }
        return (_omit_none_and_empty if omit_empty else _omit_none)(d)

    # Convenience constructor (optional)
    @staticmethod
    def aws(service: Optional[str] = None,
            productFamily: Optional[str] = None,
            region: Optional[str] = None,
            sku: Optional[str] = None,
            attributeFilters: Optional[List[AttributeFilter]] = None) -> "ProductFilter":
        return ProductFilter(
            vendorName="aws",
            service=service,
            productFamily=productFamily,
            region=region,
            sku=sku,
            attributeFilters=attributeFilters,
        )


# -----------------------------------------------------------------------------
# PriceFilter
# GraphQL keys: purchaseOption, unit, description, descriptionRegex, termLength,
#               termPurchaseOption, termOfferingClass
# NOTE: descriptionRegex must be camelCase.
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PriceFilter:
    purchaseOption: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    descriptionRegex: Optional[str] = None
    termLength: Optional[str] = None
    termPurchaseOption: Optional[str] = None
    termOfferingClass: Optional[str] = None

    def to_dict(self, omit_empty: bool = False) -> Dict[str, Any]:
        d = asdict(self)  # preserves camelCase
        return (_omit_none_and_empty if omit_empty else _omit_none)(d)

    # Convenience helpers (optional)
    @staticmethod
    def spot(unit: Optional[str] = None, descriptionRegex: Optional[str] = None) -> "PriceFilter":
        return PriceFilter(purchaseOption="spot", unit=unit, descriptionRegex=descriptionRegex)

    @staticmethod
    def on_demand(unit: Optional[str] = None, descriptionRegex: Optional[str] = None) -> "PriceFilter":
        return PriceFilter(purchaseOption="on_demand", unit=unit, descriptionRegex=descriptionRegex)
