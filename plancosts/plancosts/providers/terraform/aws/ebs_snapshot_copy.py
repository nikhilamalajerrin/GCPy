"""
Typed AWS EBS Snapshot Copy (aws_terraform).
Cost is based on the *source snapshot's* volume size:
  source_snapshot_id -> (snapshot) -> volume_id -> (volume).size
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional

from plancosts.base.filters import Filter
from .base import BaseAwsResource, BaseAwsPriceComponent, _to_decimal, DEFAULT_VOLUME_SIZE


def _ref(resource: BaseAwsResource, name: str) -> Optional[BaseAwsResource]:
    refs = resource.references()
    return refs.get(name) if isinstance(refs, dict) else None


class EbsSnapshotCopyGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsSnapshotCopy"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage Snapshot"),
            # Commit 8d1b805: anchor to end so we don't match ...UnderBilling
            Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
        ]

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()

        # Walk: source_snapshot_id -> volume_id -> size
        size = Decimal(DEFAULT_VOLUME_SIZE)
        src = _ref(self.resource(), "source_snapshot_id")
        if src:
            vol = _ref(src, "volume_id")
            if vol:
                size = _to_decimal(vol.raw_values().get("size"), Decimal(DEFAULT_VOLUME_SIZE))

        return base_hourly * size


class EbsSnapshotCopy(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._set_price_components([EbsSnapshotCopyGB("GB", self)])
