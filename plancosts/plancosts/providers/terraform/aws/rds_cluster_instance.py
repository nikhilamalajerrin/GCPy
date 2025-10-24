# plancosts/providers/terraform/aws/aws_rds_cluster_instance.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


_REGION_TO_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ca-central-1": "Canada (Central)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-central-2": "EU (Zurich)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-north-1": "EU (Stockholm)",
    "eu-south-1": "EU (Milan)",
    "eu-south-2": "EU (Spain)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-south-2": "Asia Pacific (Hyderabad)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-southeast-3": "Asia Pacific (Jakarta)",
    "ap-southeast-4": "Asia Pacific (Melbourne)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "sa-east-1": "South America (São Paulo)",
    "af-south-1": "Africa (Cape Town)",
    "me-south-1": "Middle East (Bahrain)",
    "me-central-1": "Middle East (UAE)",
}


def _region_to_location(region: Optional[str]) -> Optional[str]:
    if not region:
        return None
    return _REGION_TO_LOCATION.get(region)


def _to_db_engine(v: Any) -> str:
    s = ("" if v is None else str(v)).strip().lower()
    if s in ("", "aurora", "aurora-mysql"):
        return "Aurora MySQL"
    if s == "aurora-postgresql":
        return "Aurora PostgreSQL"
    return "Aurora MySQL"


class _RdsClusterInstanceHours(BaseAwsPriceComponent):
    def __init__(self, r: "RdsClusterInstance"):
        super().__init__(name="Database instance", resource=r, time_unit="hour")

        raw = (
            r.raw_values() if hasattr(r, "raw_values") and callable(r.raw_values) else getattr(r, "raw_values", {}) or {}
        )
        instance_type = str(raw.get("instance_class") or "").strip()
        db_engine = _to_db_engine(raw.get("engine"))
        location = _region_to_location(r.region)

        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            *( [Filter(key="location", value=location)] if location else [] ),
            Filter(key="instanceType", value=instance_type),
            Filter(key="databaseEngine", value=db_engine),
        ]

        self.set_price_filter({"purchaseOption": "on_demand"})
        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))
        self.unit_ = "hours"


class RdsClusterInstance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([_RdsClusterInstanceHours(self)])


AwsRdsClusterInstance = RdsClusterInstance
NewRdsClusterInstance = RdsClusterInstance