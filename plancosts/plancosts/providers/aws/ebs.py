"""
AWS EBS volume & snapshot pricing mappings.
Implements resource references (snapshot -> volume).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping, ValueMapping
from plancosts.base.resource import Resource


def _dec_from(v: Any, default: Decimal = Decimal(0)) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return default
    try:
        return Decimal(str(v))
    except Exception:
        return default


# -------------------------
# EBS Volume price components
# -------------------------
EbsVolumeGB = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Storage"),
        Filter(key="volumeApiName", value="gp2"),
    ],
    value_mappings=[ValueMapping(from_key="type", to_key="volumeApiName")],
    # CHANGED: (price, resource)
    calculate_cost=lambda price, resource: price * _dec_from(resource.raw_values().get("size"), Decimal(8)),
)

EbsVolumeIOPS = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="System Operation"),
        Filter(key="usagetype", value="/EBS:VolumeP-IOPS.piops/", operation="REGEX"),
        Filter(key="volumeApiName", value="gp2"),
    ],
    value_mappings=[ValueMapping(from_key="type", to_key="volumeApiName")],
    should_skip=lambda values: values.get("type") != "io1",
    # CHANGED: (price, resource)
    calculate_cost=lambda price, resource: price * _dec_from(resource.raw_values().get("iops"), Decimal(0)),
)

EbsVolume = ResourceMapping(
    price_mappings={
        "GB": EbsVolumeGB,
        "IOPS": EbsVolumeIOPS,
    }
)

# -------------------------
# EBS Snapshot price components (use references)
# -------------------------
EbsSnapshotGB = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Storage Snapshot"),
    ],
    # price * referenced volume size via references()["volume_id"]
    calculate_cost=lambda price, resource: price * _dec_from(
        (resource.references().get("volume_id").raw_values().get("size")) if resource.references().get("volume_id") else None,
        Decimal(8),
    ),
)

EbsSnapshot = ResourceMapping(
    price_mappings={
        "GB": EbsSnapshotGB,
    }
)

EbsSnapshotCopyGB = PriceMapping(
    time_unit=EbsSnapshotGB.time_unit,
    default_filters=list(EbsSnapshotGB.default_filters),
    # price * size from references()["source_snapshot_id"].references()["volume_id"].raw_values()["size"]
    calculate_cost=lambda price, resource: price * _dec_from(
        (
            resource.references().get("source_snapshot_id")
            and resource.references()["source_snapshot_id"].references().get("volume_id")
            and resource.references()["source_snapshot_id"].references()["volume_id"].raw_values().get("size")
        ),
        Decimal(8),
    ),
)

EbsSnapshot
