from __future__ import annotations

from typing import Any, Dict

from plancosts.base.filters import Filter
from plancosts.providers.terraform.aws.base import (BaseAwsPriceComponent,
                                                    BaseAwsResource)


class NatGatewayHours(BaseAwsPriceComponent):
    def __init__(self, resource: "NatGateway") -> None:
        super().__init__(name="Hours", resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="NAT Gateway"),
            Filter(key="usagetype", value="/NatGateway-Hours/", operation="REGEX"),
        ]


class NatGateway(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]) -> None:
        super().__init__(address, region, raw_values)
        self._set_price_components([NatGatewayHours(self)])
        # NAT Gateway has no sub-resources for pricing in this commit
