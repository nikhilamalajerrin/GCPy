# plancosts/providers/terraform/aws/base.py
"""
AWS Terraform typed resource/pricecomponent base classes (strict Go-port).

Matches the Go commit:
- DefaultVolumeSize
- regionMapping → used to seed region filters (locationType/location)
- BaseAwsPriceComponent: AwsResource(), TimeUnit(), Name(), Resource(), Filters(),
  SetPrice(), HourlyCost()
- BaseAwsResource: Address(), Region(), RawValues(), SubResources() (sorted),
  PriceComponents() (sorted), References(), AddReference(), HasCost()

Also includes a Python-only helper `_to_decimal` used by resource files to safely
coerce JSON-ish values to Decimal (mirrors Go's inline decimal conversions).

Extended to include Unit()/Quantity()/SetQuantityMultiplierFunc so the table can
render QUANTITY and UNIT like the Go CLI.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List

from plancosts.base.filters import Filter, ValueMapping, merge_filters, map_filters

# ----------------------------
# Constants & region mapping
# ----------------------------

DEFAULT_VOLUME_SIZE = 8  # Go: var DefaultVolumeSize = 8

REGION_MAPPING: Dict[str, str] = {
    "us-gov-west-1": "AWS GovCloud (US)",
    "us-gov-east-1": "AWS GovCloud (US-East)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ca-central-1": "Canada (Central)",
    "cn-north-1": "China (Beijing)",
    "cn-northwest-1": "China (Ningxia)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-north-1": "EU (Stockholm)",
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka-Local)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "me-south-1": "Middle East (Bahrain)",
    "sa-east-1": "South America (Sao Paulo)",
    "af-south-1": "Africa (Cape Town)",
}

# ----------------------------
# Small helpers (Python-only)
# ----------------------------

def _to_decimal(val: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Safely coerce any JSON-ish value to Decimal (Go does this inline)."""
    if isinstance(val, Decimal):
        return val
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except Exception:
        return default


def region_filters(region: str) -> List[Filter]:
    """Go's regionFilters(region) helper."""
    return [
        Filter(key="locationType", value="AWS Region"),
        Filter(key="location", value=REGION_MAPPING.get(region, "")),
    ]

# ----------------------------
# Base AWS Price Component
# ----------------------------

class BaseAwsPriceComponent:
    def __init__(self, name: str, resource: "BaseAwsResource", time_unit: str):
        self.name_: str = name
        self.resource_: BaseAwsResource = resource
        self.time_unit_: str = time_unit  # "hour" | "month"

        # Go: regionFilters seeded from regionMapping
        self.region_filters: List[Filter] = [
            Filter(key="locationType", value="AWS Region"),
            Filter(key="location", value=REGION_MAPPING.get(resource.Region(), "")),
        ]
        self.default_filters: List[Filter] = []
        self.value_mappings: List[ValueMapping] = []
        self.price_: Decimal = Decimal(0)

        # NEW: display unit + quantity fn for table (Go has SetQuantityMultiplierFunc)
        self.unit_: str = time_unit
        self._quantity_fn: Callable[["BaseAwsResource"], Decimal] = lambda r: Decimal(1)

    # ---- Go-parity methods ----
    def AwsResource(self) -> "BaseAwsResource":
        return self.resource_

    def TimeUnit(self) -> str:
        return self.time_unit_

    def Name(self) -> str:
        return self.name_

    def Resource(self) -> "BaseAwsResource":
        return self.resource_

    def Filters(self) -> List[Filter]:
        # Go: base.MapFilters(valueMappings, resource.RawValues())
        mapped = map_filters(self.value_mappings, self.resource_.RawValues())
        # Go: base.MergeFilters(regionFilters, defaultFilters, filters)
        return merge_filters(self.region_filters, self.default_filters, mapped)

    def SetPrice(self, price: Decimal) -> None:
        self.price_ = Decimal(price)

    def HourlyCost(self) -> Decimal:
        # Go logic: timeUnitSecs["hour"]/timeUnitSecs[self.time_unit_] * price
        time_unit_secs = {
            "hour": Decimal(60 * 60),
            "month": Decimal(60 * 60 * 730),
        }
        denom = time_unit_secs.get(self.time_unit_, time_unit_secs["hour"])
        try:
            multiplier = time_unit_secs["hour"] / denom
        except (InvalidOperation, ZeroDivisionError):
            multiplier = Decimal(1)
        return self.price_ * multiplier

    # NEW: Provide unit/quantity like Go now expects
    def Unit(self) -> str:
        return self.unit_

    def Quantity(self) -> Decimal:
        try:
            return self._quantity_fn(self.resource_)
        except Exception:
            return Decimal(0)

    def SetQuantityMultiplierFunc(self, fn: Callable[["BaseAwsResource"], Decimal]) -> None:
        self._quantity_fn = fn

    # --- compatibility alias used by wrappers (e.g., ASG) ---
    def get_filters(self) -> List[Filter]:
        return self.Filters()

    # ---- Python-friendly aliases (optional) ----
    def name(self) -> str:
        return self.Name()

    def resource(self) -> "BaseAwsResource":
        return self.Resource()

    def filters(self) -> List[Filter]:
        return self.Filters()

    def set_price(self, price: Decimal) -> None:
        self.SetPrice(price)

    def hourly_cost(self) -> Decimal:
        return self.HourlyCost()

    def unit(self) -> str:
        return self.Unit()

    def quantity(self) -> Decimal:
        return self.Quantity()

# ----------------------------
# Base AWS Resource
# ----------------------------

class BaseAwsResource:
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        self.address_: str = address
        self.region_: str = region
        self.raw_values_: Dict[str, Any] = raw_values or {}
        self.references_: Dict[str, "BaseAwsResource"] = {}
        self.sub_resources_: List["BaseAwsResource"] = []
        self.price_components_: List[BaseAwsPriceComponent] = []

    # ---- Go-parity methods ----
    def Address(self) -> str:
        return self.address_

    def Region(self) -> str:
        return self.region_

    def RawValues(self) -> Dict[str, Any]:
        return self.raw_values_

    def SubResources(self) -> List["BaseAwsResource"]:
        # Go sorts by Address()
        return sorted(self.sub_resources_, key=lambda r: r.Address())

    def PriceComponents(self) -> List[BaseAwsPriceComponent]:
        # Go sorts by Name()
        return sorted(self.price_components_, key=lambda pc: pc.Name())

    def References(self) -> Dict[str, "BaseAwsResource"]:
        return self.references_

    def AddReference(self, name: str, resource: "BaseAwsResource") -> None:
        self.references_[name] = resource

    def HasCost(self) -> bool:
        return True

    # ---- Python-friendly aliases ----
    def address(self) -> str:
        return self.Address()

    def region(self) -> str:
        return self.Region()

    def raw_values(self) -> Dict[str, Any]:
        return self.RawValues()

    def sub_resources(self) -> List["BaseAwsResource"]:
        return self.SubResources()

    def price_components(self) -> List[BaseAwsPriceComponent]:
        return self.PriceComponents()

    def references(self) -> Dict[str, "BaseAwsResource"]:
        return self.References()

    def add_reference(self, name: str, resource: "BaseAwsResource") -> None:
        self.AddReference(name, resource)

    def has_cost(self) -> bool:
        return self.HasCost()

    # ---- Helpers for subclasses to populate internals ----
    def _set_sub_resources(self, subs: List["BaseAwsResource"]) -> None:
        self.sub_resources_ = subs

    def _set_price_components(self, pcs: List[BaseAwsPriceComponent]) -> None:
        self.price_components_ = pcs
