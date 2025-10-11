# plancosts/providers/terraform/aws/base.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional

from plancosts.resource.filters import Filter, ValueMapping, map_filters, merge_filters

DEFAULT_VOLUME_SIZE = 8  # Go parity


def _to_decimal(val: Any, default: Decimal = Decimal(0)) -> Decimal:
    if isinstance(val, Decimal):
        return val
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except Exception:
        return default


def region_filters(region: str) -> List[Filter]:
    return []


def str_ptr(s: str) -> str:
    return s


class BaseAwsPriceComponent:
    """
    AWS-specific price component with Go-parity-ish API and helpers
    that the GraphQL query layer expects (product_filter/price_filter).
    """

    def __init__(self, name: str, resource: "BaseAwsResource", time_unit: str):
        self.name_: str = name
        self.resource_: BaseAwsResource = resource
        self.time_unit_: str = (time_unit or "hour").lower()
        self.default_filters: List[Filter] = []
        self.value_mappings: List[ValueMapping] = []
        self.price_: Decimal = Decimal(0)
        self.unit_: str = self.time_unit_
        self._quantity_fn: Callable[[BaseAwsResource], Decimal] = lambda r: Decimal(1)

        self._price_filter_dict: Optional[Dict[str, Any]] = None
        self._product_filter_override: Optional[Dict[str, Any]] = None

    # ---- Go-parity-ish ----
    def AwsResource(self) -> "BaseAwsResource":
        return self.resource_

    def TimeUnit(self) -> str:
        return self.time_unit_

    def Name(self) -> str:
        return self.name_

    def Resource(self) -> "BaseAwsResource":
        return self.resource_

    def Filters(self) -> List[Filter]:
        mapped = map_filters(self.value_mappings, self.resource_.RawValues())
        return merge_filters(self.default_filters, mapped)

    # unit price storage
    def SetPrice(self, price: Decimal) -> None:
        self.price_ = _to_decimal(price, Decimal(0))

    def Price(self) -> Decimal:
        return self.price_

    # compatibility alias for tests (pc.price_component.price())
    def price(self) -> Decimal:
        return self.Price()

    def HourlyCost(self) -> Decimal:
        return self.calculate_hourly_cost(self.price_)

    # ---- Quantity/Unit (for table) ----
    def Unit(self) -> str:
        return self.unit_

    def Quantity(self) -> Decimal:
        qty = Decimal(1)
        try:
            qty = self._quantity_fn(self.resource_)
        except Exception:
            qty = Decimal(1)

        time_unit_secs = {
            "hour": Decimal(60 * 60),
            "month": Decimal(60 * 60 * 730),
        }
        month = time_unit_secs["month"]
        tu = time_unit_secs.get(self.time_unit_, month)
        try:
            time_unit_multiplier = month / tu
        except (InvalidOperation, ZeroDivisionError):
            time_unit_multiplier = Decimal(1)

        count = Decimal(self.resource_.ResourceCount() if hasattr(self.resource_, "ResourceCount") else 1)
        return (qty * time_unit_multiplier * count).quantize(Decimal("0.000001"))

    def SetQuantityMultiplierFunc(self, fn: Callable[["BaseAwsResource"], Decimal]) -> None:
        self._quantity_fn = fn

    # --- convenience aliases ---
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
    #  GraphQL Query helpers
    # ----------------------------
    def _synth_product_filter(self) -> Dict[str, Any]:
        """
        Build a Go-like ProductFilter and SKIP empty/None values in attributeFilters.
        This prevents over-constraining queries like {"databaseEdition": ""}.
        """
        if self._product_filter_override is not None:
            return dict(self._product_filter_override)

        service = None
        product_family = None
        attrs: List[Dict[str, Any]] = []

        for f in self.Filters():
            k = (f.key or "").strip()
            if not k:
                continue

            # Lift common fields
            if k.lower() == "servicecode" and f.value:
                service = str(f.value)
                continue
            if k == "productFamily" and f.value:
                product_family = str(f.value)
                continue

            # Prepare attribute entry — skip empty values
            op = (f.operation or "").upper()
            v = "" if f.value is None else str(f.value)
            if not v:
                continue

            if op == "REGEX":
                attrs.append({"key": k, "valueRegex": v})
            else:
                attrs.append({"key": k, "value": v})

        return {
            "vendorName": "aws",
            "service": service,
            "productFamily": product_family,
            "region": self.resource_.Region() if hasattr(self.resource_, "Region") else None,
            "attributeFilters": attrs or None,
        }

    def product_filter(self) -> Dict[str, Any]:
        return self._synth_product_filter()

    def set_product_filter_override(self, pf: Optional[Dict[str, Any]]) -> None:
        self._product_filter_override = dict(pf) if pf else None

    def price_filter(self) -> Optional[Dict[str, Any]]:
        return dict(self._price_filter_dict) if isinstance(self._price_filter_dict, dict) else None

    def set_price_filter(self, pf: Optional[Dict[str, Any]]) -> None:
        self._price_filter_dict = dict(pf) if pf else None

    # ----------------------------
    #  Math helpers for wrappers
    # ----------------------------
    def calculate_hourly_cost(self, unit_price: Decimal) -> Decimal:
        """
        Convert a unit price (per time_unit_) to hourly and scale by quantity.
        Only round at the end to avoid magnifying errors in monthly math.
        """
        unit_price = _to_decimal(unit_price, Decimal(0))
        time_unit_secs = {
            "hour": Decimal(60 * 60),
            "month": Decimal(60 * 60 * 730),
        }
        hour = time_unit_secs["hour"]
        month = time_unit_secs["month"]
        try:
            month_to_hour = hour / month  # 1/730
        except (InvalidOperation, ZeroDivisionError):
            month_to_hour = Decimal(1)

        hourly = unit_price * self.Quantity() * month_to_hour
        # Quantize to 10 dp to match API price granularity and satisfy equality checks
        return hourly.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)


class BaseAwsResource:
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        self.address_: str = address
        self.region_: str = region
        self.raw_values_: Dict[str, Any] = raw_values or {}
        self.references_: Dict[str, "BaseAwsResource"] = {}
        self.sub_resources_: List["BaseAwsResource"] = []
        self.price_components_: List[BaseAwsPriceComponent] = []
        self._has_cost: bool = True
        self._resource_count: int = 1

    # ---- Go-parity-ish ----
    def Address(self) -> str:
        return self.address_

    def Region(self) -> str:
        return self.region_

    def RawValues(self) -> Dict[str, Any]:
        return self.raw_values_

    def SubResources(self) -> List["BaseAwsResource"]:
        # Preserve insertion order to match expected test ordering
        return list(self.sub_resources_)

    def PriceComponents(self) -> List[BaseAwsPriceComponent]:
        # Preserve insertion order
        return list(self.price_components_)

    def References(self) -> Dict[str, "BaseAwsResource"]:
        return self.references_

    def AddReference(self, name: str, resource: "BaseAwsResource") -> None:
        self.references_[name] = resource

    def HasCost(self) -> bool:
        return self._has_cost

    def ResourceCount(self) -> int:
        return self._resource_count

    def SetResourceCount(self, count: int) -> None:
        self._resource_count = int(count)

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

    # ---- helpers for subclasses ----
    def _set_sub_resources(self, subs: List["BaseAwsResource"]) -> None:
        self.sub_resources_ = subs

    def _set_price_components(self, pcs: List[BaseAwsPriceComponent]) -> None:
        self.price_components_ = pcs

    def _set_has_cost(self, has_cost: bool) -> None:
        self._has_cost = bool(has_cost)
