# plancosts/providers/terraform/aws/rds_instance.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.resource.filters import Filter, ValueMapping
from plancosts.resource.resource import PriceComponent, Resource
from .base import BaseAwsPriceComponent, BaseAwsResource

# Map multi_az -> deploymentOption
_MULTI_AZ = ValueMapping(
    from_key="multi_az",
    to_key="deploymentOption",
    map_func=lambda v: "Multi-AZ" if bool(v) else "Single-AZ",
)

# Helper: infer volumeType from storage_type (and iops fallback)
def _storage_type_to_volume_type(v: Any) -> str:
    sv = ("" if v is None else str(v)).strip()
    if sv == "standard":
        return "Magnetic"
    if sv == "io1":
        return "Provisioned IOPS"
    # default
    return "General Purpose"


class RdsStorageIOPS(BaseAwsPriceComponent):
    def __init__(self, r: "RdsInstance"):
        super().__init__("IOPS", r, "month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="deploymentOption", value="Single-AZ"),
        ]
        self.value_mappings = [_MULTI_AZ]
        # Quantity = IOPS value (default 0)
        self.SetQuantityMultiplierFunc(
            lambda res: Decimal(str(res.raw_values().get("iops") or 0))
        )
        self.unit_ = "IOPS/month"


class RdsStorageGB(BaseAwsPriceComponent):
    def __init__(self, r: "RdsInstance"):
        super().__init__("GB", r, "month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Storage"),
            Filter(key="deploymentOption", value="Single-AZ"),
            Filter(key="volumeType", value="General Purpose"),
        ]
        self.value_mappings = [
            ValueMapping(
                from_key="storage_type",
                to_key="volumeType",
                map_func=_storage_type_to_volume_type,
            ),
            _MULTI_AZ,
        ]
        # Quantity = allocated or max_allocated storage (GB), default 0
        self.SetQuantityMultiplierFunc(
            lambda res: Decimal(
                str(
                    res.raw_values().get("max_allocated_storage")
                    or res.raw_values().get("allocated_storage")
                    or 0
                )
            )
        )
        self.unit_ = "GB/month"


class RdsInstanceHours(BaseAwsPriceComponent):
    def __init__(self, r: "RdsInstance"):
        # Match Go label exactly: "instance hours (<instance_class>)"
        it = r.raw_values().get("instance_class") or ""
        label = f"instance hours ({it})" if it else "instance hours"
        super().__init__(label, r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            Filter(key="deploymentOption", value="Single-AZ"),
        ]
        self.value_mappings = [
            # instance_class -> instanceType
            ValueMapping(from_key="instance_class", to_key="instanceType"),
            # engine -> databaseEngine
            ValueMapping(
                from_key="engine",
                to_key="databaseEngine",
                map_func=lambda e: {
                    # include both "postgres" and "postgresql"
                    "postgres": "PostgreSQL",
                    "postgresql": "PostgreSQL",
                    "mysql": "MySQL",
                    "mariadb": "MariaDB",
                    "aurora": "Aurora MySQL",
                    "aurora-mysql": "Aurora MySQL",
                    "aurora-postgresql": "Aurora PostgreSQL",
                    "oracle-se": "Oracle",
                    "oracle-se1": "Oracle",
                    "oracle-se2": "Oracle",
                    "oracle-ee": "Oracle",
                    "sqlserver-ex": "SQL Server",
                    "sqlserver-web": "SQL Server",
                    "sqlserver-se": "SQL Server",
                    "sqlserver-ee": "SQL Server",
                }.get(str(e).lower(), ""),
            ),
            # engine -> databaseEdition (only for Oracle/SQL Server families)
            ValueMapping(
                from_key="engine",
                to_key="databaseEdition",
                map_func=lambda e: {
                    "oracle-se": "Standard",
                    "sqlserver-se": "Standard",
                    "oracle-se1": "Standard One",
                    "oracle-se2": "Standard 2",
                    "oracle-ee": "Enterprise",
                    "sqlserver-ee": "Enterprise",
                    "sqlserver-ex": "Express",
                    "sqlserver-web": "Web",
                }.get(str(e).lower(), ""),
            ),
            _MULTI_AZ,
        ]
        # Hours PC has quantity = 1 per hour
        self.SetQuantityMultiplierFunc(lambda _: Decimal(1))


class RdsInstance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        pcs: List[PriceComponent] = [RdsInstanceHours(self), RdsStorageGB(self)]

        # If storage_type is explicitly io1 OR storage_type unset but iops set, add IOPS
        st = (raw_values or {}).get("storage_type")
        if st == "io1" or (st is None and raw_values.get("iops") is not None):
            pcs.append(RdsStorageIOPS(self))

        self._set_price_components(pcs)