# # plancosts/providers/terraform/aws/ebs_snapshot.py
# from __future__ import annotations

# from decimal import Decimal
# from typing import Any, Dict, Optional, Callable

# from plancosts.resource.filters import Filter
# from .base import (
#     DEFAULT_VOLUME_SIZE,
#     BaseAwsPriceComponent,
#     BaseAwsResource,
#     _to_decimal,
# )


# def _raw(values_or_res: Any) -> Dict[str, Any]:
#     """
#     Normalize to a plain dict of raw values from either a resource, a dict,
#     or a callable returning a dict.
#     """
#     try:
#         vals = getattr(values_or_res, "raw_values", values_or_res)
#         if callable(vals):
#             vals = vals() or {}
#         return dict(vals or {})
#     except Exception:
#         return {}


# class _EbsSnapshotStorageGB(BaseAwsPriceComponent):
#     """
#     Mirrors ebsSnapshotCostComponents() from Go:

#     - Name:  "Storage"
#     - Unit:  "GB-months"
#     - Quantity resolution (robust order):
#         1) cached referenced volume size (captured at construction from rd.References("volume_id"))
#         2) this snapshot's explicit 'size'
#         3) DEFAULT_VOLUME_SIZE (8 GB)

#     - Product filter:
#         servicecode=AmazonEC2
#         productFamily="Storage Snapshot"
#         usagetype ~= /EBS:SnapshotUsage$/
#     """
#     def __init__(self, resource: "EbsSnapshot"):
#         super().__init__(name="Storage", resource=resource, time_unit="month")

#         self.default_filters = [
#             Filter(key="servicecode", value="AmazonEC2"),
#             Filter(key="productFamily", value="Storage Snapshot"),
#             # REGEX to match "...EBS:SnapshotUsage" (end of string), like Go
#             Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
#         ]
#         self.unit_ = "GB-months"

#         # Prefer a cached size from referenced volume if constructor found one.
#         cached = getattr(resource, "_cached_volume_size", None)
#         if cached is not None:
#             try:
#                 self._cached_qty = _to_decimal(cached, Decimal(DEFAULT_VOLUME_SIZE))
#             except Exception:
#                 self._cached_qty = Decimal(DEFAULT_VOLUME_SIZE)
#         else:
#             self._cached_qty = None

#         def _quantity(res: BaseAwsResource) -> Decimal:
#             # 1) Cached ref volume size
#             if self._cached_qty is not None:
#                 return self._cached_qty

#             # 2) Fallback: this snapshot's explicit 'size'
#             size = _raw(res).get("size")
#             if size is not None:
#                 return _to_decimal(size, Decimal(DEFAULT_VOLUME_SIZE))

#             # 3) Default
#             return Decimal(DEFAULT_VOLUME_SIZE)

#         self._monthly_quantity_fn: Callable[[BaseAwsResource], Decimal] = _quantity
#         self.SetQuantityMultiplierFunc(_quantity)

#     # Helpers some tests look for
#     def MonthlyQuantity(self) -> Decimal:
#         try:
#             return self._monthly_quantity_fn(self.resource)
#         except Exception:
#             return Decimal(0)

#     @property
#     def monthly_quantity(self) -> Decimal:
#         return self.MonthlyQuantity()


# class EbsSnapshot(BaseAwsResource):
#     """
#     Python port of internal/providers/terraform/aws/ebs_snapshot.go (NewEbsSnapshot):

#     - Single "Storage" GB-months component with usagetype REGEX match.
#     - Quantity derived from the referenced volume's size when available.
#     """
#     def __init__(self, address: str, region: str, raw_values: Dict[str, Any], rd: Optional[Any] = None):
#         # Accept rd so the parser’s (address, region, raw, rd) path works and references can be read.
#         try:
#             super().__init__(address=address, region=region, raw_values=raw_values, rd=rd)  # type: ignore[call-arg]
#         except TypeError:
#             super().__init__(address=address, region=region, raw_values=raw_values)

#         # --- Cache the referenced volume size using ResourceData references ---
#         self._cached_volume_size: Optional[Any] = None
#         try:
#             # rd.References("volume_id") returns a list of referenced ResourceData
#             if rd is not None and hasattr(rd, "References"):
#                 refs = rd.References("volume_id") or []
#                 if refs:
#                     vol_rd = refs[0]
#                     raw = getattr(vol_rd, "raw_values", None)
#                     if callable(raw):
#                         raw = raw() or {}
#                     if isinstance(raw, dict):
#                         self._cached_volume_size = raw.get("size")
#         except Exception:
#             # Best-effort; leave as None if anything goes wrong.
#             pass

#         self._set_price_components([_EbsSnapshotStorageGB(self)])


# # Optional export alias like Go’s constructor name if needed elsewhere
# NewEbsSnapshot = EbsSnapshot







# plancosts/providers/terraform/aws/ebs_snapshot.py
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
    """
    Normalize to a plain dict of raw values from either a resource, a dict,
    or a callable returning a dict.
    """
    try:
        vals = getattr(values_or_res, "raw_values", values_or_res)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}


class _EbsSnapshotStorageGB(BaseAwsPriceComponent):
    """
    Mirrors ebsSnapshotCostComponents() from Go:

    - Name:  "Storage"
    - Unit:  "GB-Mo"  (catalog commonly uses GB-Mo for snapshots)
    - Quantity resolution (robust order):
        1) cached referenced volume size (captured at construction from rd.References("volume_id"))
        2) this snapshot's explicit 'size'
        3) DEFAULT_VOLUME_SIZE (8 GB)

    - Product filter:
        servicecode matches AmazonEC2 or AmazonEBS (catalog variations)
        productFamily="Storage Snapshot"
        usagetype ~= /EBS:SnapshotUsage$/
    """
    def __init__(self, resource: "EbsSnapshot"):
        super().__init__(name="Storage", resource=resource, time_unit="month")

        self.default_filters = [
            # Some catalogs expose snapshots under AmazonEC2, others as AmazonEBS.
            Filter(key="servicecode", value="/Amazon(EC2|EBS)/", operation="REGEX"),
            Filter(key="productFamily", value="Storage Snapshot"),
            # REGEX to match "...EBS:SnapshotUsage" (end of string)
            Filter(key="usagetype", value="/EBS:SnapshotUsage$/", operation="REGEX"),
        ]
        # IMPORTANT: snapshots are priced as GB-Mo in many catalogs.
        self.unit_ = "GB-Mo"

        # Prefer a cached size from referenced volume if constructor found one.
        cached = getattr(resource, "_cached_volume_size", None)
        if cached is not None:
            try:
                self._cached_qty = _to_decimal(cached, Decimal(DEFAULT_VOLUME_SIZE))
            except Exception:
                self._cached_qty = Decimal(DEFAULT_VOLUME_SIZE)
        else:
            self._cached_qty = None

        def _quantity(res: BaseAwsResource) -> Decimal:
            # 1) Cached ref volume size
            if self._cached_qty is not None:
                return self._cached_qty

            # 2) Fallback: this snapshot's explicit 'size'
            size = _raw(res).get("size")
            if size is not None:
                return _to_decimal(size, Decimal(DEFAULT_VOLUME_SIZE))

            # 3) Default
            return Decimal(DEFAULT_VOLUME_SIZE)

        self._monthly_quantity_fn: Callable[[BaseAwsResource], Decimal] = _quantity
        self.SetQuantityMultiplierFunc(_quantity)

    # Helpers some tests look for
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
    Python port of internal/providers/terraform/aws/ebs_snapshot.go (NewEbsSnapshot):

    - Single "Storage" GB-months component with usagetype REGEX match.
    - Quantity derived from the referenced volume's size when available.
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], rd: Optional[Any] = None):
        # Accept rd so the parser’s (address, region, raw, rd) path works and references can be read.
        try:
            super().__init__(address=address, region=region, raw_values=raw_values, rd=rd)  # type: ignore[call-arg]
        except TypeError:
            super().__init__(address=address, region=region, raw_values=raw_values)

        # --- Cache the referenced volume size using ResourceData references ---
        self._cached_volume_size: Optional[Any] = None
        try:
            # rd.References("volume_id") returns a list of referenced ResourceData
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
            # Best-effort; leave as None if anything goes wrong.
            pass

        self._set_price_components([_EbsSnapshotStorageGB(self)])


# Optional export alias like Go’s constructor name if needed elsewhere
NewEbsSnapshot = EbsSnapshot
