# plancosts/providers/terraform/aws/lb.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Tuple

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


# ---------------- helpers ----------------

def _safe_call_or_value(obj: Any) -> Any:
    if callable(obj):
        try:
            return obj()
        except Exception:
            return {}
    return obj

def _vals(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    raw = getattr(obj, "raw_values", {})
    raw = _safe_call_or_value(raw)
    return raw or {}

def _kind(obj: Any) -> Tuple[str, str]:
    values = _vals(obj)
    lb_type = str(values.get("load_balancer_type", "application")).lower()
    if lb_type == "network":
        return ("Per Network Load Balancer", "Load Balancer-Network")
    return ("Per Application Load Balancer", "Load Balancer-Application")


# ---------------- price component ----------------

class _LbHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Lb"):
        name, product_family = _kind(resource)
        super().__init__(name=name, resource=resource, time_unit="hour")

        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            Filter(key="productFamily", value=product_family),
            Filter(key="usagetype", value="LoadBalancerUsage"),
        ]
        self.set_price_filter({"unit": "Hrs", "purchaseOption": "on_demand"})

        def _qty(_r: "Lb") -> Decimal:
            new_name, new_family = _kind(_r)
            self._name = new_name
            for f in self.default_filters:
                if getattr(f, "key", "") == "productFamily":
                    setattr(f, "value", new_family)
                    break
            return Decimal(1)

        self.SetQuantityMultiplierFunc(_qty)
        self.unit_ = "hours"


# ---------------- resource ----------------

class Lb(BaseAwsResource):
    """
    Mirrors GetLBRegistryItem/NewLB in Go:
      - Handles aws_lb and aws_alb aliases
      - Builds one hourly "Per [Application|Network] Load Balancer" component
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([_LbHours(self)])


# --- Export aliases for registry compatibility ---
AwsLb = Lb
NewLb = Lb
