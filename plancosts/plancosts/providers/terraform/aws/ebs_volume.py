"""
Typed AWS EBS Volume resource & components (aws_terraform).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.base.filters import Filter, ValueMapping

from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)

# ----------------------------
# Price components
# ----------------------------


class EbsVolumeGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsVolume"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value="gp2"),
        ]
        self.value_mappings = [ValueMapping(from_key="type", to_key="volumeApiName")]

    def hourly_cost(self) -> Decimal:
        # base monthly → hourly conversion
        base_hourly = super().hourly_cost()
        # multiply by GB size
        size = _to_decimal(
            self.resource().raw_values().get("size"), Decimal(DEFAULT_VOLUME_SIZE)
        )
        return base_hourly * size


class EbsVolumeIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsVolume"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            Filter(
                key="usagetype", value="/EBS:VolumeP-IOPS.piops/", operation="REGEX"
            ),
            Filter(key="volumeApiName", value="gp2"),
        ]
        self.value_mappings = [ValueMapping(from_key="type", to_key="volumeApiName")]

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()
        iops = _to_decimal(self.resource().raw_values().get("iops"), Decimal(0))
        return base_hourly * iops


# ----------------------------
# Resource
# ----------------------------


class EbsVolume(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)

        pcs: List[BaseAwsPriceComponent] = [EbsVolumeGB("GB", self)]
        # Only include IOPS for io1 (io2 would be different pricing; matching the Go commit behavior)
        if self.raw_values().get("type") == "io1":
            pcs.append(EbsVolumeIOPS("IOPS", self))

        self._set_price_components(pcs)
