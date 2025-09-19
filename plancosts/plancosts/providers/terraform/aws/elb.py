from __future__ import annotations
from typing import Dict, Any, List

from plancosts.base.filters import Filter, ValueMapping
from plancosts.base.resource import Resource, PriceComponent
from plancosts.providers.terraform.aws.base import BaseAwsResource, BaseAwsPriceComponent


class ElbHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Elb", is_classic: bool) -> None:
        super().__init__(name="Hours", resource=resource, time_unit="hour")
        # Common filters
        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            # productFamily depends on classic vs ALB/NLB
            Filter(key="productFamily", value="Load Balancer" if is_classic else "Load Balancer-Application"),
            # Usage type is a regex in the Go code
            Filter(key="usagetype", value="/LoadBalancerUsage/", operation="REGEX"),
        ]

        # For ALB/NLB we map load_balancer_type to productFamily
        if not is_classic:
            self.value_mappings = [
                ValueMapping(
                    from_key="load_balancer_type",
                    to_key="productFamily",
                    map_func=lambda v: (
                        "Load Balancer-Network" if f"{v}" == "network" else "Load Balancer-Application"
                    ),
                )
            ]


class Elb(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], is_classic: bool) -> None:
        super().__init__(address, region, raw_values)
        self._price_components: List[PriceComponent] = [ElbHours(self, is_classic)]
        self._sub_resources: List[Resource] = []

    def price_components(self) -> List[PriceComponent]:
        return list(self._price_components)

    def sub_resources(self) -> List[Resource]:
        return list(self._sub_resources)
