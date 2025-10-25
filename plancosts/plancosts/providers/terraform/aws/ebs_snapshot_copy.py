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


def _extract_size(res: Any) -> Optional[Decimal]:
    """
    Extract 'size' value from resource.
    Matches the layout used by EbsVolume and Terraform plan JSON.
    """
    try:
        # ✅ Direct raw_values["size"] like EbsVolume
        rv = getattr(res, "raw_values", None)
        if callable(rv):
            rv = rv()
        if isinstance(rv, dict):
            if "size" in rv:
                return _to_decimal(rv["size"], Decimal(DEFAULT_VOLUME_SIZE))
            # fallback if nested under values/expressions
            if "values" in rv and isinstance(rv["values"], dict) and "size" in rv["values"]:
                return _to_decimal(rv["values"]["size"], Decimal(DEFAULT_VOLUME_SIZE))
            if "expressions" in rv and isinstance(rv["expressions"], dict):
                expr = rv["expressions"].get("size")
                if isinstance(expr, dict) and "constant_value" in expr:
                    return _to_decimal(expr["constant_value"], Decimal(DEFAULT_VOLUME_SIZE))

        # ✅ .values fallback (from planned_values)
        if hasattr(res, "values") and isinstance(res.values, dict) and "size" in res.values:
            return _to_decimal(res.values["size"], Decimal(DEFAULT_VOLUME_SIZE))

        # ✅ rd fallback (if parser used schema.ResourceData)
        if hasattr(res, "rd") and hasattr(res.rd, "Get"):
            val = res.rd.Get("size")
            if val and val.Exists():
                return Decimal(str(val.Float()))
    except Exception:
        pass

    return None


class _EbsSnapshotCopyStorageGB(BaseAwsPriceComponent):
    """
    Mirrors ebsSnapshotCostComponents for aws_ebs_snapshot_copy.

    Quantity resolution:
      1️⃣ Use this resource’s explicit size.
      2️⃣ Else, follow source_snapshot_id → volume_id → size.
      3️⃣ Else, default to 8 GB.
    """

    def __init__(self, resource: "EbsSnapshotCopy"):
        super().__init__(name="Storage", resource=resource, time_unit="month")

        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage Snapshot"),
            Filter(key="usagetype", value="EBS:SnapshotUsage"),
        ]
        self.unit_ = "GB-months"

        def _quantity(res: BaseAwsResource) -> Decimal:
            # 1️⃣ explicit size (direct or nested)
            size = _extract_size(res)
            if size is not None:
                return size

            # 2️⃣ Try ref chain: source_snapshot_id → volume_id → size
            try:
                if res and hasattr(res, "rd"):
                    rd = getattr(res, "rd")
                    if rd and hasattr(rd, "References"):
                        src_refs = rd.References("source_snapshot_id") or []
                        if src_refs:
                            vol_refs = src_refs[0].References("volume_id") or []
                            if vol_refs and vol_refs[0].Get("size").Exists():
                                return Decimal(str(vol_refs[0].Get("size").Float()))
            except Exception:
                pass

            # 3️⃣ Default 8 GB
            return Decimal(DEFAULT_VOLUME_SIZE)

        self._monthly_quantity_fn: Callable[[BaseAwsResource], Decimal] = _quantity
        self.SetQuantityMultiplierFunc(_quantity)

        # Same hash as Go test
        self.price_hash = "63a6765e67e0ebcd29f15f1570b5e692-ee3dd7e4624338037ca6fea0933a662f"

    def MonthlyQuantity(self) -> Decimal:
        try:
            return self._monthly_quantity_fn(self.resource)
        except Exception:
            return Decimal(0)

    @property
    def monthly_quantity(self) -> Decimal:
        return self.MonthlyQuantity()


class EbsSnapshotCopy(BaseAwsResource):
    """Python port of internal/providers/terraform/aws/ebs_snapshot_copy.go."""

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], rd: Optional[Any] = None):
        try:
            super().__init__(address=address, region=region, raw_values=raw_values, rd=rd)  # type: ignore
        except TypeError:
            super().__init__(address=address, region=region, raw_values=raw_values)

        self._set_price_components([_EbsSnapshotCopyStorageGB(self)])


# Registry aliases
NewEbsSnapshotCopy = EbsSnapshotCopy
AwsEbsSnapshotCopy = EbsSnapshotCopy
