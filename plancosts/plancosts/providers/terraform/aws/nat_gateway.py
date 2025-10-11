from __future__ import annotations

from typing import Any, Dict

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


class NatGatewayHours(BaseAwsPriceComponent):
    def __init__(self, resource: "NatGateway") -> None:
        # commit parity: lowercase "hours"
        super().__init__(name="hours", resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="NAT Gateway"),
            # exact match works with pricing.infracost.io
            Filter(key="usagetype", value="NatGateway-Hours"),
        ]
        self.SetQuantityMultiplierFunc(lambda _: 1)


class NatGateway(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([NatGatewayHours(self)])
