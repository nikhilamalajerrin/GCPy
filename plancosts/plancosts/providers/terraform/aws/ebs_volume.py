# plancosts/providers/terraform/aws/ebs_volume.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.resource.filters import Filter, ValueMapping
from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)


class EbsVolumeGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsVolume"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value="gp2"),
        ]
        self.value_mappings = [ValueMapping(from_key="type", to_key="volumeApiName")]
        self.SetQuantityMultiplierFunc(
            lambda r: _to_decimal(r.raw_values().get("size"), Decimal(DEFAULT_VOLUME_SIZE))
        )
        self.unit_ = "GB/month"


class EbsVolumeIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsVolume"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            # Target Provisioned IOPS usage directly; some catalogs omit volumeApiName here.
            Filter(key="usagetype", value="EBS:VolumeP-IOPS.piops"),
        ]
        # Quantity = IOPS value
        self.SetQuantityMultiplierFunc(
            lambda r: _to_decimal(r.raw_values().get("iops"), Decimal(0))
        )
        self.unit_ = "IOPS/month"


class EbsVolume(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        pcs: List[BaseAwsPriceComponent] = [EbsVolumeGB("GB", self)]
        # Add IOPS component for both io1 and io2 volumes
        if str(self.raw_values().get("type") or "") in ("io1", "io2"):
            pcs.append(EbsVolumeIOPS("IOPS", self))
        self._set_price_components(pcs)
