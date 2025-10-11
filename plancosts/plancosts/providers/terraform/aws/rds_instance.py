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

# Map Terraform license_model -> AWS licenseModel
_LICENSE_MODEL = ValueMapping(
    from_key="license_model",
    to_key="licenseModel",
    map_func=lambda v: {
        "license-included": "License included",
        "bring-your-own-license": "Bring your own license",
        "byol": "Bring your own license",
    }.get(str(v).lower(), ""),
)

# Map engine -> databaseEngine (used for instance-hours only)
_ENGINE_TO_DBENGINE = ValueMapping(
    from_key="engine",
    to_key="databaseEngine",
    map_func=lambda e: {
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
)

# Map engine -> databaseEdition (instance-hours only; Oracle/SQL Server families)
_ENGINE_TO_DBEDITION = ValueMapping(
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
)

# Infer volumeType from storage_type
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
        # NOTE: Do NOT add engine/edition here — storage SKUs usually don't have them.
        # Keep license model as some catalogs split by it.
        self.value_mappings = [
            _MULTI_AZ,
            _LICENSE_MODEL,
        ]
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
        # NOTE: Do NOT add engine/edition here — storage SKUs usually don't have them.
        # Include storage type mapping + license model for disambiguation where present.
        self.value_mappings = [
            ValueMapping(
                from_key="storage_type",
                to_key="volumeType",
                map_func=_storage_type_to_volume_type,
            ),
            _MULTI_AZ,
            _LICENSE_MODEL,
        ]
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
        it = r.raw_values().get("instance_class") or ""
        label = f"instance hours ({it})" if it else "instance hours"
        super().__init__(label, r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            Filter(key="deploymentOption", value="Single-AZ"),
        ]
        self.value_mappings = [
            ValueMapping(from_key="instance_class", to_key="instanceType"),
            _ENGINE_TO_DBENGINE,
            _ENGINE_TO_DBEDITION,
            _MULTI_AZ,
            _LICENSE_MODEL,
        ]
        self.SetQuantityMultiplierFunc(lambda _: Decimal(1))


class RdsInstance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        pcs: List[PriceComponent] = [RdsInstanceHours(self), RdsStorageGB(self)]

        # Add IOPS if needed
        st = (raw_values or {}).get("storage_type")
        if st == "io1" or (st is None and raw_values.get("iops") is not None):
            pcs.append(RdsStorageIOPS(self))

        self._set_price_components(pcs)
