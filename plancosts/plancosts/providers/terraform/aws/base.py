# plancosts/providers/aws_terraform/base.py
"""
AWS Terraform typed resource/pricecomponent base classes (Python port).

Mirrors the Go commit that introduced:
- AwsResource / AwsPriceComponent interfaces
- BaseAwsResource / BaseAwsPriceComponent implementations
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Dict, List, Any

from plancosts.base.filters import Filter, merge_filters
from plancosts.base.filters import ValueMapping

# ----------------------------
# Constants & region mapping
# ----------------------------

DEFAULT_VOLUME_SIZE = 8  # GiB

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
# Internal helpers
# ----------------------------

def _to_decimal(val: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Safely coerce any JSON-ish value to Decimal."""
    if isinstance(val, Decimal):
        return val
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except Exception:
        return default


def _value_mapped_filters(value_mappings: List[ValueMapping], values: Dict[str, Any]) -> List[Filter]:
    """Map raw values to pricing filters using ValueMapping rules."""
    out: List[Filter] = []
    for vm in value_mappings:
        if vm.from_key in values:
            to_val = vm.mapped_value(values[vm.from_key])
            if to_val:
                out.append(Filter(key=vm.to_key, value=to_val))
    return out


# ----------------------------
# Base AWS Price Component
# ----------------------------

class BaseAwsPriceComponent:
    def __init__(self, name: str, resource: "BaseAwsResource", time_unit: str):
        self._name = name
        self._resource = resource
        self._time_unit = time_unit  # "hour" | "month"
        self._default_filters: List[Filter] = []
        self._value_mappings: List[ValueMapping] = []
        self._price: Decimal = Decimal(0)

        location = REGION_MAPPING.get(resource.region(), "")
        self._region_filters: List[Filter] = [
            Filter(key="locationType", value="AWS Region"),
            Filter(key="location", value=location),
        ]

    # --- Go-parity style accessors ---
    def AwsResource(self) -> "BaseAwsResource":
        return self._resource

    def TimeUnit(self) -> str:
        return self._time_unit

    def Name(self) -> str:
        return self._name

    # Back-compat names used by other parts of the codebase
    def get_filters(self):
        return self.Filters()

    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        self.SetPrice(price)
        return self.HourlyCost()

    def Resource(self) -> "BaseAwsResource":
        return self._resource

    def Filters(self) -> List[Filter]:
        mapped = _value_mapped_filters(self._value_mappings, self._resource.raw_values())
        return merge_filters(self._region_filters, self._default_filters, mapped)

    def SetPrice(self, price: Decimal) -> None:
        self._price = price

    def HourlyCost(self) -> Decimal:
        secs = {"hour": Decimal(3600), "month": Decimal(3600 * 730)}
        denom = secs.get(self._time_unit) or Decimal(3600)
        try:
            return self._price * (secs["hour"] / denom)
        except (InvalidOperation, ZeroDivisionError):
            return self._price

    # --- Python-friendly aliases/back-compat (no skip_query anymore) ---
    def aws_resource(self) -> "BaseAwsResource":
        return self.AwsResource()

    def time_unit(self) -> str:
        return self.TimeUnit()

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

    # --- Mutables for subclasses ---
    @property
    def default_filters(self) -> List[Filter]:
        return self._default_filters

    @default_filters.setter
    def default_filters(self, v: List[Filter]) -> None:
        self._default_filters = v

    @property
    def value_mappings(self) -> List[ValueMapping]:
        return self._value_mappings

    @value_mappings.setter
    def value_mappings(self, v: List[ValueMapping]) -> None:
        self._value_mappings = v


# ----------------------------
# Base AWS Resource
# ----------------------------

class BaseAwsResource:
    """
    Minimal resource base used by typed AWS resources.
    Manages address, region, raw values, references, subresources, and components.
    """

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        self._address = address
        self._region = region
        self._raw_values = raw_values or {}
        self._references: Dict[str, "BaseAwsResource"] = {}
        self._sub_resources: List["BaseAwsResource"] = []
        self._price_components: List[BaseAwsPriceComponent] = []

    # --- Required interface methods (Go parity) ---

    def Address(self) -> str:
        return self._address

    def Region(self) -> str:
        return self._region

    def RawValues(self) -> Dict[str, Any]:
        return self._raw_values

    def SubResources(self) -> List["BaseAwsResource"]:
        return self._sub_resources

    def PriceComponents(self) -> List[BaseAwsPriceComponent]:
        return self._price_components

    def References(self) -> Dict[str, "BaseAwsResource"]:
        return self._references

    def AddReference(self, name: str, resource: "BaseAwsResource") -> None:
        self._references[name] = resource

    def HasCost(self) -> bool:
        return True

    # --- Python-friendly aliases/back-compat ---

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

    # --- Helpers for subclasses to populate internals ---

    def _set_sub_resources(self, subs: List["BaseAwsResource"]) -> None:
        self._sub_resources = subs

    def _set_price_components(self, pcs: List[BaseAwsPriceComponent]) -> None:
        self._price_components = pcs
