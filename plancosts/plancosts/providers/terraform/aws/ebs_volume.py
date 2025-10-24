# plancosts/providers/terraform/aws/ebs_volume.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource, DEFAULT_VOLUME_SIZE


class _EbsStorage(BaseAwsPriceComponent):
    """
    Name: "Storage"
    Unit: "GB-months"
    Product: AmazonEC2 → Storage
    Attribute: volumeApiName = gp2/gp3/io1/io2/standard
    """
    def __init__(self, resource: "EbsVolume", region: str, volume_type: str, gb_val: Decimal):
        super().__init__("Storage", resource, "month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value=volume_type),
        ]
        self.unit_ = "GB-months"
        self.SetQuantityMultiplierFunc(lambda _r: gb_val)


class _EbsIOPS(BaseAwsPriceComponent):
    """
    Name: "Storage IOPS"
    Unit: "IOPS-months"
    Product: AmazonEC2 → System Operation
    Attribute: volumeApiName=io1/io2, usagetype=EBS:VolumeP-IOPS.piops
    """
    def __init__(self, resource: "EbsVolume", region: str, volume_type: str, iops_val: Decimal):
        super().__init__("Storage IOPS", resource, "month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            Filter(key="volumeApiName", value=volume_type),
            Filter(key="usagetype", value="/EBS:VolumeP-IOPS.piops/", operation="REGEX"),
        ]
        self.unit_ = "IOPS-months"
        self.SetQuantityMultiplierFunc(lambda _r: iops_val)


class EbsVolume(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/ebs_volume::NewEBSVolume
    - Storage (GB-months)
    - Storage IOPS (IOPS-months) for io1 volumes
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        volume_type = str(raw_values.get("type") or "gp2")
        gb_val = Decimal(str(raw_values.get("size") or DEFAULT_VOLUME_SIZE))
        iops_val = Decimal(str(raw_values.get("iops") or 0))

        pcs: List[BaseAwsPriceComponent] = [_EbsStorage(self, region, volume_type, gb_val)]

        if volume_type == "io1":
            pcs.append(_EbsIOPS(self, region, volume_type, iops_val))

        self._set_price_components(pcs)


AwsEbsVolume = EbsVolume
NewEbsVolume = EbsVolume
