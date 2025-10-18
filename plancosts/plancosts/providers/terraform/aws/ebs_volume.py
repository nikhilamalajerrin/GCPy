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

def _raw(res_or_values: Any) -> Dict[str, Any]:
    """
    Return a plain dict of raw values.
    Accepts either a resource (with .raw_values) or a dict/callable returning a dict.
    """
    try:
        vals = getattr(res_or_values, "raw_values", res_or_values)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}

def _vol_api_name(values: Any) -> str:
    """
    Map Terraform 'type' (or 'volume_type') to the pricing 'volumeApiName'.
    Default to gp2.
    """
    v = _raw(values)
    t = (v.get("type") or v.get("volume_type") or v.get("volumeType") or "gp2")
    t = str(t).lower()
    mapping = {
        "gp2": "gp2",
        "gp3": "gp3",
        "io1": "io1",
        "io2": "io2",
        "st1": "st1",
        "sc1": "sc1",
        "standard": "standard",   # aka magnetic
        "magnetic": "standard",
    }
    return mapping.get(t, "gp2")

def _gb_val(values: Any) -> Decimal:
    # Terraform arg is 'size' (not volume_size). Default to 8 GB.
    v = _raw(values)
    return _to_decimal(v.get("size"), Decimal(DEFAULT_VOLUME_SIZE))

def _iops_val(values: Any) -> Decimal:
    # Default IOPS equals default volume size (8), matching Go change.
    v = _raw(values)
    return _to_decimal(v.get("iops"), Decimal(DEFAULT_VOLUME_SIZE))

class _EbsVolumeStorageGB(BaseAwsPriceComponent):
    """
    Name:  "Storage"
    Unit:  "GB-months"
    Product: AmazonEC2 / Storage, attribute volumeApiName (mapped from 'type')
    Qty:   size (default 8)
    """
    def __init__(self, r: "EbsVolume"):
        super().__init__(name="Storage", resource=r, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value=_vol_api_name(r)),
        ]
        # map Terraform 'type' -> pricing 'volumeApiName'
        self.value_mappings = [ValueMapping(from_key="type", to_key="volumeApiName")]
        # quantity is 'size' (default 8)
        self.SetQuantityMultiplierFunc(lambda res: _gb_val(res))
        self.unit_ = "GB-months"

class _EbsVolumeIOPS(BaseAwsPriceComponent):
    """
    Name:  "Storage IOPS"
    Unit:  "IOPS-months"
    Only added for io1 volumes.
    Product: AmazonEC2 / System Operation
    Attrs:  volumeApiName, usagetype regex /EBS:VolumeP-IOPS.piops/
    Qty:    iops (default 8)
    """
    def __init__(self, r: "EbsVolume"):
        super().__init__(name="Storage IOPS", resource=r, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            # Use regex operation like other resources (no value_regex kw)
            Filter(key="usagetype", value="/EBS:VolumeP-IOPS\\.piops/", operation="REGEX"),
            Filter(key="volumeApiName", value=_vol_api_name(r)),
        ]
        self.value_mappings = [ValueMapping(from_key="type", to_key="volumeApiName")]
        self.SetQuantityMultiplierFunc(lambda res: _iops_val(res))
        self.unit_ = "IOPS-months"

class EbsVolume(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/ebs_volume.go:
      - Storage (GB-months) w/ volumeApiName from 'type', qty from 'size'
      - Storage IOPS (IOPS-months) only when type == 'io1', qty from 'iops'
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)

        pcs: List[BaseAwsPriceComponent] = [_EbsVolumeStorageGB(self)]
        if _vol_api_name(self) == "io1":
            pcs.append(_EbsVolumeIOPS(self))

        self._set_price_components(pcs)

# Optional alias like Go’s constructor name
NewEbsVolume = EbsVolume
