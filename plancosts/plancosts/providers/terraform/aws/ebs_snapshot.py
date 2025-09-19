"""
Typed AWS EBS Snapshot resources (aws_terraform).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional

from plancosts.base.filters import Filter
from .base import BaseAwsResource, BaseAwsPriceComponent, _to_decimal, DEFAULT_VOLUME_SIZE


def _ref(resource: BaseAwsResource, name: str) -> Optional[BaseAwsResource]:
    refs = resource.references()
    return refs.get(name) if isinstance(refs, dict) else None


class EbsSnapshotGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsSnapshot"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage Snapshot"),
            # Commit 8d1b805: anchor to end so we don't match ...UnderBilling
            Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
        ]

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()
        vol = _ref(self.resource(), "volume_id")
        size = _to_decimal((vol.raw_values().get("size") if vol else None), Decimal(DEFAULT_VOLUME_SIZE))
        return base_hourly * size


class EbsSnapshot(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._set_price_components([EbsSnapshotGB("GB", self)])
