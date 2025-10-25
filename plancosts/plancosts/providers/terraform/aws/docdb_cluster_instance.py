# plancosts/providers/terraform/aws/docdb_cluster_instance.py
from __future__ import annotations
from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import BaseAwsResource, BaseAwsPriceComponent

if TYPE_CHECKING:
    from plancosts.schema.resource_data import ResourceData


class DocdbClusterInstance(BaseAwsResource):
    """
    Cost model for aws_docdb_cluster_instance.

    Components:
      - Database instance (on-demand, <instance_class>)
      - Storage (GB-months)
      - I/O (requests)
      - Backup storage (GB-months)
      - CPU credits (for db.t3.*)
    """

    SERVICE = "AmazonDocDB"

    def __init__(self, d: "ResourceData", u: Optional["ResourceData"] = None) -> None:
        self.d = d
        self.u = u

        # --- region ---
        try:
            get = getattr(d, "Get", None)
            if callable(get):
                self.region = get("region").String()
            else:
                self.region = str(d.get("region", ""))
        except Exception:
            self.region = ""

        # --- instance class ---
        try:
            if callable(get):
                self.instance_type = get("instance_class").String()
            else:
                self.instance_type = str(d.get("instance_class", ""))
        except Exception:
            self.instance_type = ""

        super().__init__(address=getattr(d, "Address", ""), region=self.region, raw_values={})

    def name(self) -> str:
        return getattr(self.d, "Address", "")

    # ------------------------
    # Price components builder
    # ------------------------
    def price_components(self) -> List[BaseAwsPriceComponent]:
        pcs: List[BaseAwsPriceComponent] = []

        # Database instance
        pcs.append(
            self._pc(
                name=f"Database instance (on-demand, {self.instance_type})",
                time_unit="hour",
                product_family="Database Instance",
                attr_filters={"instanceType": self.instance_type},
                purchase_option="on_demand",
                fixed_qty=Decimal(1),
            )
        )

        # Storage
        pcs.append(
            self._pc(
                name="Storage",
                time_unit="month",
                product_family="Database Storage",
                attr_filters={"usagetype": "StorageUsage"},
                purchase_option="on_demand",
            )
        )

        # I/O
        pcs.append(
            self._pc(
                name="I/O",
                time_unit="month",
                product_family="System Operation",
                attr_filters={"usagetype": "StorageIOUsage"},
            )
        )

        # Backup storage
        pcs.append(
            self._pc(
                name="Backup storage",
                time_unit="month",
                product_family="Storage Snapshot",
                attr_filters={"usagetype": "BackupUsage"},
            )
        )

        # CPU credits (for db.t3.*)
        if self.instance_type.startswith("db.t3."):
            pcs.append(
                self._pc(
                    name="CPU credits",
                    time_unit="hour",
                    product_family="CPU Credits",
                    attr_filters={"usagetype": "CPUCredits:db.t3"},
                )
            )

        self._set_price_components(pcs)
        return pcs

    # ------------------------
    # Helper
    # ------------------------
    def _pc(
        self,
        *,
        name: str,
        time_unit: str,
        product_family: str,
        attr_filters: Optional[Dict[str, str]] = None,
        purchase_option: Optional[str] = None,
        fixed_qty: Optional[Decimal] = None,
    ) -> BaseAwsPriceComponent:
        pc = BaseAwsPriceComponent(name, self, time_unit)

        attribute_filters: List[Dict[str, Any]] = [
            {"key": k, "value": v} for k, v in (attr_filters or {}).items()
        ]

        product_filter = {
            "vendorName": "aws",
            "region": self.region or None,
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


def NewDocdbClusterInstance(d: "ResourceData", u: Optional["ResourceData"] = None) -> DocdbClusterInstance:
    return DocdbClusterInstance(d, u)
