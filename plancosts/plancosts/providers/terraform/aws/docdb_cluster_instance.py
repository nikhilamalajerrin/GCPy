from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import BaseAwsResource, BaseAwsPriceComponent

if TYPE_CHECKING:
    # type-only; keep import graph clean
    from plancosts.schema.resource_data import ResourceData


class DocdbClusterInstance(BaseAwsResource):
    """
    Cost model for aws_docdb_cluster_instance (Python port of the Go version).

    Components:
      - Database Instance (on_demand, hours) filtered by instanceType
      - Storage (GB-months) usagetype=StorageUsage (on_demand)
      - I/O (requests) usagetype=StorageIOUsage
      - Backup Storage (GB-months) usagetype=BackupUsage
      - CPU Credits (vCPU-hours) for db.t3.* (usagetype=CPUCredits:db.t3)
    """

    SERVICE = "AmazonDocDB"

    # NOTE: We don't call BaseAwsResource.__init__ here since unit tests provide a FakeRD.
    # We just store minimal state needed by name()/price_components().
    def __init__(self, d: "ResourceData", u: Optional["ResourceData"] = None) -> None:
        self.d = d
        self.u = u
        self.region: str = d.get("region", "") if hasattr(d, "get") else ""
        self.instance_type: str = d.get("instance_class", "") if hasattr(d, "get") else ""

    def name(self) -> str:
        return getattr(self.d, "Address", "")

    # ------------- public: build cost components -------------
    def price_components(self) -> List[BaseAwsPriceComponent]:
        pcs: List[BaseAwsPriceComponent] = []

        # 1) On-demand instance hours (time unit=hour)
        pcs.append(
            self._pc(
                name=f"Database Instance (on_demand, {self.instance_type})",
                time_unit="hour",
                product_family="Database Instance",
                attr_filters={"instanceType": self.instance_type},
                purchase_option="on_demand",
                fixed_qty=Decimal(1),  # 1 instance-hour per hour
            )
        )

        # 2) Storage (GB-months) -> time unit=month
        pcs.append(
            self._pc(
                name="Storage",
                time_unit="month",
                product_family="Database Storage",
                attr_filters={"usagetype": "StorageUsage"},
                purchase_option="on_demand",
            )
        )

        # 3) I/O (requests) -> time unit=month (requests priced per-request; quantity supplied by usage)
        pcs.append(
            self._pc(
                name="I/O",
                time_unit="month",
                product_family="System Operation",
                attr_filters={"usagetype": "StorageIOUsage"},
            )
        )

        # 4) Backup Storage (GB-months) -> time unit=month
        pcs.append(
            self._pc(
                name="Backup Storage",
                time_unit="month",
                product_family="Storage Snapshot",
                attr_filters={"usagetype": "BackupUsage"},
            )
        )

        # 5) CPU credits for db.t3.* -> time unit=hour
        if self.instance_type.startswith("db.t3."):
            pcs.append(
                self._pc(
                    name="CPU Credits",
                    time_unit="hour",
                    product_family="CPU Credits",
                    attr_filters={"usagetype": "CPUCredits:db.t3"},
                )
            )

        return pcs

    # ----------------- helpers -----------------
    def _pc(
        self,
        *,
        name: str,
        time_unit: str,  # "hour" | "month"
        product_family: str,
        attr_filters: Optional[Dict[str, str]] = None,
        purchase_option: Optional[str] = None,
        fixed_qty: Optional[Decimal] = None,
    ) -> BaseAwsPriceComponent:
        """
        Create a BaseAwsPriceComponent wired for our base.py contract:
        - constructor: (name, resource, time_unit)
        - set product/price filter via setters
        - quantity via SetQuantityMultiplierFunc
        """
        pc = BaseAwsPriceComponent(name, self, time_unit)

        # Attribute filters are a list of {"key":..., "value":...} or {"key":..., "valueRegex":...}
        attribute_filters: List[Dict[str, Any]] = []
        for k, v in (attr_filters or {}).items():
            attribute_filters.append({"key": k, "value": v})

        product_filter: Dict[str, Any] = {
            "vendorName": "aws",
            "region": (self.region or None),
            "service": self.SERVICE,
            "productFamily": product_family,
            "attributeFilters": attribute_filters or None,
        }
        pc.set_product_filter_override(product_filter)

        if purchase_option:
            pc.set_price_filter({"purchaseOption": purchase_option})

        if isinstance(fixed_qty, Decimal):
            pc.SetQuantityMultiplierFunc(lambda _r: fixed_qty)

        return pc


# Optional factory alias
def NewDocdbClusterInstance(d: "ResourceData", u: Optional["ResourceData"] = None) -> DocdbClusterInstance:
    return DocdbClusterInstance(d, u)
