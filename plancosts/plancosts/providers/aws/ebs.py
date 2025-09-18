"""
AWS EBS volume & snapshot pricing mappings with safe reference guards.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping, ValueMapping

def _num(val, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return default

# --- existing volume mappings (keep yours if already present) ---
EbsVolumeGB = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Storage"),
        Filter(key="volumeApiName", value="gp2"),
    ],
    value_mappings=[ValueMapping(from_key="type", to_key="volumeApiName")],
    calculate_cost=lambda price, resource: price * (_num((resource.raw_values() or {}).get("size"), Decimal(8))),
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
    calculate_cost=lambda price, resource: price * _num((resource.raw_values() or {}).get("iops"), Decimal(0)),
)
EbsVolume = ResourceMapping(price_mappings={"GB": EbsVolumeGB, "IOPS": EbsVolumeIOPS})

# --- snapshots (SAFE) ---
def _ref(resource, key: str):
    """Safe getter for a reference by name."""
    refs = resource.references()
    return refs.get(key) if isinstance(refs, dict) else None

EbsSnapshotGB = PriceMapping(
    time_unit="month",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Storage Snapshot"),
    ],
    calculate_cost=lambda price, resource: price * _num(
        (_ref(resource, "volume_id").raw_values().get("size")) if _ref(resource, "volume_id") else None,
        Decimal(8),
    ),
)
EbsSnapshot = ResourceMapping(price_mappings={"GB": EbsSnapshotGB})

EbsSnapshotCopyGB = PriceMapping(
    time_unit=EbsSnapshotGB.time_unit,
    default_filters=list(EbsSnapshotGB.default_filters),
    calculate_cost=lambda price, resource: price * _num(
        (
            _ref(_ref(resource, "source_snapshot_id"), "volume_id").raw_values().get("size")
            if _ref(resource, "source_snapshot_id") and _ref(_ref(resource, "source_snapshot_id"), "volume_id")
            else None
        ),
        Decimal(8),
    ),
)
EbsSnapshotCopy = ResourceMapping(price_mappings={"GB": EbsSnapshotCopyGB})
