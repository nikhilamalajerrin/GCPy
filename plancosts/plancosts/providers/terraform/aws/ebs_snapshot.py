from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Callable

from plancosts.resource.filters import Filter
from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)


def _raw(values_or_res: Any) -> Dict[str, Any]:
    """Return plain dict of raw values from resource or mapping."""
    try:
        vals = getattr(values_or_res, "raw_values", values_or_res)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}


class _EbsSnapshotStorageGB(BaseAwsPriceComponent):
    """
    Mirrors ebsSnapshotCostComponents():

    - Name:  "Storage"
    - Unit:  "GB-months"
    - Product filter:
        vendorName = aws
        service    = AmazonEC2
        productFamily = "Storage Snapshot"
        usagetype  ~= /EBS:SnapshotUsage$/
    """

    def __init__(self, resource: "EbsSnapshot"):
        super().__init__(name="Storage", resource=resource, time_unit="month")

        # match Go logic exactly
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage Snapshot"),
            Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
        ]
        self.unit_ = "GB-months"

        cached = getattr(resource, "_cached_volume_size", None)
        if cached is not None:
            try:
                self._cached_qty = _to_decimal(cached, Decimal(DEFAULT_VOLUME_SIZE))
            except Exception:
                self._cached_qty = Decimal(DEFAULT_VOLUME_SIZE)
        else:
            self._cached_qty = None

        def _quantity(res: BaseAwsResource) -> Decimal:
            if self._cached_qty is not None:
                return self._cached_qty
            size = _raw(res).get("size")
            if size is not None:
                return _to_decimal(size, Decimal(DEFAULT_VOLUME_SIZE))
            return Decimal(DEFAULT_VOLUME_SIZE)

        self._monthly_quantity_fn: Callable[[BaseAwsResource], Decimal] = _quantity
        self.SetQuantityMultiplierFunc(_quantity)

    def MonthlyQuantity(self) -> Decimal:
        try:
            return self._monthly_quantity_fn(self.resource)
        except Exception:
            return Decimal(0)

    @property
    def monthly_quantity(self) -> Decimal:
        return self.MonthlyQuantity()


class EbsSnapshot(BaseAwsResource):
    """
    Python equivalent of internal/providers/terraform/aws/ebs_snapshot.go

    - Uses referenced volume size if available.
    - Adds a single "Storage" component (GB-months).
    """

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], rd: Optional[Any] = None):
        try:
            super().__init__(address=address, region=region, raw_values=raw_values, rd=rd)  # type: ignore
        except TypeError:
            super().__init__(address=address, region=region, raw_values=raw_values)

        # cache volume size from reference
        self._cached_volume_size: Optional[Any] = None
        try:
            if rd is not None and hasattr(rd, "References"):
                refs = rd.References("volume_id") or []
                if refs:
                    vol_rd = refs[0]
                    raw = getattr(vol_rd, "raw_values", None)
                    if callable(raw):
                        raw = raw() or {}
                    if isinstance(raw, dict):
                        self._cached_volume_size = raw.get("size")
        except Exception:
            pass

        self._set_price_components([_EbsSnapshotStorageGB(self)])


NewEbsSnapshot = EbsSnapshot
AwsEbsSnapshot = EbsSnapshot
