# plancosts/providers/terraform/aws/elb.py
from __future__ import annotations

from typing import Any, Dict

from plancosts.resource.filters import Filter, ValueMapping
from .base import BaseAwsPriceComponent, BaseAwsResource


class ElbHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Elb", is_classic: bool) -> None:
        super().__init__(name="Hours", resource=resource, time_unit="hour")

        default_family = "Load Balancer" if is_classic else "Load Balancer-Application"

        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            Filter(key="productFamily", value=default_family),
            Filter(key="usagetype", value="LoadBalancerUsage"),  # Exact match
        ]

        if not is_classic:
            self.value_mappings = [
                ValueMapping(
                    from_key="load_balancer_type",
                    to_key="productFamily",
                    map_func=lambda v: "Load Balancer-Network"
                    if str(v) == "network"
                    else "Load Balancer-Application",
                )
            ]

        self.SetQuantityMultiplierFunc(lambda _: 1)


class Elb(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], is_classic: bool) -> None:
        super().__init__(address, region, raw_values)
        self._set_price_components([ElbHours(self, is_classic)])