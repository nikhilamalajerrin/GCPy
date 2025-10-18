# plancosts/providers/terraform/aws/lb.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Tuple

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


# ---------------- helpers ----------------

def _safe_call_or_value(obj: Any) -> Any:
    """Return obj() if callable, else obj; swallow exceptions and return {}."""
    if callable(obj):
        try:
            return obj()
        except Exception:
            return {}
    return obj

def _vals(obj: Any) -> Dict[str, Any]:
    """
    Return the raw values dict whether it's exposed as:
      - a dict attribute 'raw_values'
      - a callable method 'raw_values()'
      - already a dict
    """
    if isinstance(obj, dict):
        return obj
    raw = getattr(obj, "raw_values", {})
    raw = _safe_call_or_value(raw)
    return raw or {}


def _kind(obj: Any) -> Tuple[str, str]:
    """
    Return (costComponentName, productFamily) based on load_balancer_type.
      - application -> ("Per Application Load Balancer", "Load Balancer-Application")
      - network     -> ("Per Network Load Balancer",      "Load Balancer-Network")
    Default to 'application'.
    """
    values = _vals(obj)
    lb_type = str(values.get("load_balancer_type", "application")).lower()
    if lb_type == "network":
        return ("Per Network Load Balancer", "Load Balancer-Network")
    return ("Per Application Load Balancer", "Load Balancer-Application")


# ---------------- price component ----------------

class _LbHours(BaseAwsPriceComponent):
    """
    Hourly charge for aws_lb (ALB/NLB).
    - Name & productFamily depend on load_balancer_type.
    - Unit: hours, Quantity: 1/hour.

    Product filter:
      servicecode=AWSELB
      productFamily=(Load Balancer-Application|Load Balancer-Network)
      usagetype=LoadBalancerUsage          <-- selects the plain hourly SKU

    Price filter:
      unit="Hrs", purchaseOption="on_demand"
    """
    def __init__(self, resource: "Lb"):
        name, product_family = _kind(resource)
        super().__init__(name=name, resource=resource, time_unit="hour")

        # Narrow to the hourly usage SKU (exclude LCU/Reserved/Outposts/Trust Store).
        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            Filter(key="productFamily", value=product_family),
            Filter(key="usagetype", value="LoadBalancerUsage"),
        ]

        # Select the right price row via unit/purchase option.
        self.set_price_filter({
            "unit": "Hrs",
            "purchaseOption": "on_demand",
        })

        # Keep name/productFamily in sync if raw_values change.
        def _qty(_r: "Lb") -> Decimal:
            new_name, new_family = _kind(_r)
            self._name = new_name
            for f in self.default_filters:
                if getattr(f, "key", "") == "productFamily":
                    setattr(f, "value", new_family)
                    break
            return Decimal(1)

        self.SetQuantityMultiplierFunc(_qty)
        # Display unit; catalog unit is "Hrs", but our user-facing string is "hours".
        self.unit_ = "hours"


# ---------------- resource ----------------

class Lb(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/lb.go:
      - ALB/NLB hourly component with dynamic name/product family from load_balancer_type.
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([_LbHours(self)])


# Optional alias if any code imports AwsLb
AwsLb = Lb
