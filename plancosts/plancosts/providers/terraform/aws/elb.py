from __future__ import annotations

from typing import Any, Dict, List

from plancosts.resource.filters import Filter, ValueMapping
from plancosts.resource.resource import PriceComponent, Resource
from .base import BaseAwsPriceComponent, BaseAwsResource

class ElbHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Elb", is_classic: bool) -> None:
        super().__init__(name="Hours", resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AWSELB"),
            Filter(key="productFamily", value="Load Balancer" if is_classic else "Load Balancer-Application"),
            Filter(key="usagetype", value="/LoadBalancerUsage/", operation="REGEX"),
        ]
        if not is_classic:
            self.value_mappings = [
                ValueMapping(
                    from_key="load_balancer_type",
                    to_key="productFamily",
                    map_func=lambda v: "Load Balancer-Network" if f"{v}" == "network" else "Load Balancer-Application",
                )
            ]
        self.unit_ = "hour"
        self.SetQuantityMultiplierFunc(lambda r: 1)

class Elb(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], is_classic: bool) -> None:
        super().__init__(address, region, raw_values)
        self._price_components: List[PriceComponent] = [ElbHours(self, is_classic)]
        self._sub_resources: List[Resource] = []

    def price_components(self) -> List[PriceComponent]:
        return list(self._price_components)

    def sub_resources(self) -> List[Resource]:
        return list(self._sub_resources)
