# plancosts/providers/terraform/aws/nat_gateway.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


def _to_decimal(x: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _extract_usage_value(usage: Dict[str, Any], key: str) -> Optional[Decimal]:
    """
    Extract a numeric value from usage[key] supporting shapes like:
      - plain number:                      {"key": 123}
      - dict with 'value':                 {"key": {"value": 123}}
      - dict with index '0'.value:         {"key": {"0": {"value": 123}}}
      - list of dicts with 'value':        {"key": [{"value": 123}, ...]}
    Returns Decimal or None if not found.
    """
    if key not in usage or usage[key] is None:
        return None

    v = usage[key]

    # Simple number/str
    d = _to_decimal(v, None)  # type: ignore[arg-type]
    if isinstance(d, Decimal):
        return d

    # Dict forms
    if isinstance(v, dict):
        # { "value": 123 }
        if "value" in v:
            return _to_decimal(v["value"], None)
        # { "0": {"value": 123}, ... }
        z = v.get("0")
        if isinstance(z, dict) and "value" in z:
            return _to_decimal(z["value"], None)
        # Fall back: first nested dict that has 'value'
        for sub in v.values():
            if isinstance(sub, dict) and "value" in sub:
                return _to_decimal(sub["value"], None)

    # List forms: [ {"value": 123}, ... ]
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict) and "value" in first:
            return _to_decimal(first["value"], None)

    return None


class _NatGatewayHours(BaseAwsPriceComponent):
    """
    Name: "Per NAT Gateway"
    Unit: "hours"
    Quantity: 1 per hour
    ProductFilter: service=AmazonEC2, productFamily=NAT Gateway, usagetype="NatGateway-Hours"
    """
    def __init__(self, resource: "NatGateway"):
        super().__init__(name="Per NAT Gateway", resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="NAT Gateway"),
            Filter(key="usagetype", value="NatGateway-Hours"),
        ]
        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))
        self.unit_ = "hours"


class _NatGatewayDataProcessed(BaseAwsPriceComponent):
    """
    Name: "Per GB data processed"
    Unit: "GB"
    Quantity: monthly GB; defaults to 0 unless usage is provided.
    ProductFilter: service=AmazonEC2, productFamily=NAT Gateway, usagetype="NatGateway-Bytes"
    """

    _USAGE_KEYS = (
        "gb_data_processed_monthly",  
        "monthly_gb_data_processed",
        "gb_data_processed",
        "data_processed_gb",
        "nat_gateway_gb",
    )

    def __init__(self, resource: "NatGateway"):
        super().__init__(name="Per GB data processed", resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="NAT Gateway"),
            Filter(key="usagetype", value="NatGateway-Bytes"),
        ]
        self.SetQuantityMultiplierFunc(self._quantity_from_usage)
        self.unit_ = "GB"

    def _quantity_from_usage(self, r: "NatGateway") -> Decimal:
        usage: Optional[Dict[str, Any]] = None
        if hasattr(r, "usage") and callable(getattr(r, "usage")):
            usage = r.usage()
        elif hasattr(r, "_usage"):
            usage = getattr(r, "_usage")
        else:
            usage = None

        if not isinstance(usage, dict):
            return Decimal(0)

        for k in self._USAGE_KEYS:
            val = _extract_usage_value(usage, k)
            if isinstance(val, Decimal):
                return val
        return Decimal(0)


class NatGateway(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/nat_gateway
      - Hourly NAT GW charge ("NatGateway-Hours")
      - Per-GB data processed ("NatGateway-Bytes")
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([
            _NatGatewayHours(self),
            _NatGatewayDataProcessed(self),
        ])


AwsNatGateway = NatGateway
NewNatGateway = NatGateway
