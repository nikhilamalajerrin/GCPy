# plancosts/providers/terraform/aws/elb.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


class _ElbClassicHours(BaseAwsPriceComponent):
    """
    Classic ELB hourly charge.

    Name:          "Per Classic Load Balancer"
    Unit:          "hours"
    Time unit:     hour   (framework will convert to monthly where needed)
    Filters:
      - servicecode:   AWSELB
      - productFamily: Load Balancer
      - usagetype:     LoadBalancerUsage
    Quantity: 1 per hour (no usage needed)
    """
    def __init__(self, resource: "Elb"):
        super().__init__(name="Per Classic Load Balancer", resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            Filter(key="productFamily", value="Load Balancer"),
            Filter(key="usagetype", value="LoadBalancerUsage"),
        ]
        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))
        self.unit_ = "hours"


class Elb(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/elb::NewELB.

    This models **Classic ELB** (aws_elb), not Application/Network Load Balancers.
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([_ElbClassicHours(self)])
