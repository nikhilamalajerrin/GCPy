"""
AWS EBS volume pricing mappings.

Parities with Go (internal/aws/ebs.go):
- EbsVolumeGB: TimeUnit="month", default filters, type→volumeApiName mapping,
  CalculateCost(price, values): price * size (default 8 GiB if missing)
- EbsVolumeIOPS: TimeUnit="month", default filters (incl. usagetype REGEX),
  type→volumeApiName, ShouldSkip unless type == "io1",
  CalculateCost(price, values): price * iops
- EbsVolume resource aggregates GB and IOPS components
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping, ValueMapping


def _decimal_from_any(v: Any, default: Decimal = Decimal(0)) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return default
    try:
        return Decimal(str(v))
    except Exception:
        return default


EbsVolumeGB = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Storage"),
        Filter(key="volumeApiName", value="gp2"),
    ],
    value_mappings=[
        ValueMapping(from_key="type", to_key="volumeApiName"),
    ],
    calculate_cost=lambda price, values: price * _decimal_from_any(values.get("size"), Decimal(8)),
)

EbsVolumeIOPS = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="System Operation"),
        Filter(key="usagetype", value="/EBS:VolumeP-IOPS.piops/", operation="REGEX"),
        Filter(key="volumeApiName", value="gp2"),
    ],
    value_mappings=[
        ValueMapping(from_key="type", to_key="volumeApiName"),
    ],
    should_skip=lambda values: values.get("type") != "io1",
    calculate_cost=lambda price, values: price * _decimal_from_any(values.get("iops"), Decimal(0)),
)

EbsVolume = ResourceMapping(
    price_mappings={
        "GB": EbsVolumeGB,
        "IOPS": EbsVolumeIOPS,
    }
)
