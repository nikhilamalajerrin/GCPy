from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.base.filters import Filter, ValueMapping
from plancosts.base.resource import PriceComponent, Resource
from plancosts.providers.terraform.aws.base import (
    BaseAwsPriceComponent,
    BaseAwsResource,
)

# Map multi_az -> deploymentOption
_MULTI_AZ = ValueMapping(
    from_key="multi_az",
    to_key="deploymentOption",
    map_func=lambda v: "Multi-AZ" if bool(v) else "Single-AZ",
)


class RdsStorageIOPS(PriceComponent):
    def __init__(self, r: "RdsInstance"):
        self._inner = BaseAwsPriceComponent("IOPS", r, "month")
        self._inner.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="deploymentOption", value="Single-AZ"),
        ]
        self._inner.value_mappings = [_MULTI_AZ]

    # delegate required API
    def name(self):
        return self._inner.Name()

    def resource(self) -> Resource:
        return self._inner.Resource()

    def filters(self):
        return self._inner.Filters()

    def set_price(self, p):
        self._inner.SetPrice(p)

    def hourly_cost(self):
        base = self._inner.HourlyCost()
        iops = self.resource().raw_values().get("iops") or 0
        return base * Decimal(str(iops))


class RdsStorageGB(PriceComponent):
    def __init__(self, r: "RdsInstance"):
        self._inner = BaseAwsPriceComponent("GB", r, "month")
        self._inner.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Storage"),
            Filter(key="deploymentOption", value="Single-AZ"),
            Filter(key="volumeType", value="General Purpose"),
        ]
        self._inner.value_mappings = [
            ValueMapping(
                from_key="storage_type",
                to_key="volumeType",
                map_func=lambda v: {
                    "standard": "Magnetic",
                    "io1": "Provisioned IOPS",
                }.get(str(v), "General Purpose"),
            ),
            _MULTI_AZ,
        ]

    def name(self):
        return self._inner.Name()

    def resource(self) -> Resource:
        return self._inner.Resource()

    def filters(self):
        return self._inner.Filters()

    def set_price(self, p):
        self._inner.SetPrice(p)

    def hourly_cost(self):
        base = self._inner.HourlyCost()
        vals = self.resource().raw_values()
        size = vals.get("max_allocated_storage") or vals.get("allocated_storage") or 0
        return base * Decimal(str(size))


class RdsInstanceHours(PriceComponent):
    def __init__(self, r: "RdsInstance"):
        self._inner = BaseAwsPriceComponent("Instance hours", r, "hour")
        self._inner.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            Filter(key="deploymentOption", value="Single-AZ"),
        ]
        self._inner.value_mappings = [
            ValueMapping(from_key="instance_class", to_key="instanceType"),
            ValueMapping(
                from_key="engine",
                to_key="databaseEngine",
                map_func=lambda e: {
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

    def name(self):
        return self._inner.Name()

    def resource(self) -> Resource:
        return self._inner.Resource()

    def filters(self):
        return self._inner.Filters()

    def set_price(self, p):
        self._inner.SetPrice(p)

    def hourly_cost(self):
        return self._inner.HourlyCost()


class RdsInstance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        pcs: List[PriceComponent] = [RdsInstanceHours(self), RdsStorageGB(self)]
        if self.raw_values().get("storage_type") == "io1":
            pcs.append(RdsStorageIOPS(self))
        self._set_price_components(pcs)
