# plancosts/providers/terraform/aws/aws_rds_cluster_instance.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource

def _to_db_engine(v: Any) -> str:
    s = ("" if v is None else str(v)).strip().lower()
    if s in ("", "aurora", "aurora-mysql"):
        return "Aurora MySQL"
    if s == "aurora-postgresql":
        return "Aurora PostgreSQL"
    return "Aurora MySQL"

class _RdsClusterInstanceHours(BaseAwsPriceComponent):
    """
    Name:  "Database instance"
    Unit:  hours (qty = 1/hour)
    Service: AmazonRDS
    ProductFamily: Database Instance
    Attribute filters: instanceType, databaseEngine
    """
    def __init__(self, r: "RdsClusterInstance"):
        super().__init__(name="Database instance", resource=r, time_unit="hour")

        raw = r.raw_values() if hasattr(r, "raw_values") and callable(r.raw_values) else getattr(r, "raw_values", {}) or {}
        instance_type = str(raw.get("instance_class") or "")
        db_engine = _to_db_engine(raw.get("engine"))

        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            Filter(key="instanceType", value=instance_type),
            Filter(key="databaseEngine", value=db_engine),
        ]

        # Keep on-demand to avoid RI/savings-plan prices accidentally matching
        self.set_price_filter({"purchaseOption": "on_demand"})

        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))
        self.unit_ = "hours"

class RdsClusterInstance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([_RdsClusterInstanceHours(self)])


AwsRdsClusterInstance = RdsClusterInstance
