from __future__ import annotations

from decimal import Decimal
from typing import Dict, Optional

from plancosts.resource.filters import Filter

from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)

def _ref(resource: BaseAwsResource, name: str) -> Optional[BaseAwsResource]:
    refs = resource.references()
    return refs.get(name) if isinstance(refs, dict) else None

class EbsSnapshotGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "EbsSnapshot"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage Snapshot"),
            Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
        ]
        self.unit_ = "GB/month"
        def _q(res: BaseAwsResource) -> Decimal:
            vol = _ref(res, "volume_id")
            return _to_decimal(
                (vol.RawValues().get("size") if vol else None),
                Decimal(DEFAULT_VOLUME_SIZE),
            )
        self.SetQuantityMultiplierFunc(_q)

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()
        vol = _ref(self.resource(), "volume_id")
        size = _to_decimal(
            (vol.raw_values().get("size") if vol else None),
            Decimal(DEFAULT_VOLUME_SIZE),
        )
        return base_hourly * size

class EbsSnapshot(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._set_price_components([EbsSnapshotGB("GB", self)])
