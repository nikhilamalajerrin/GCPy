from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


# ---------------- helpers ----------------

def _to_decimal(x: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return default

def _to_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in ("1", "true", "yes", "y", "on")

def _rv_of(resource: BaseAwsResource) -> Dict[str, Any]:
    """Return a plain dict for the resource's raw values, regardless of getter style."""
    rv_attr = getattr(resource, "raw_values", None)
    try:
        return rv_attr() if callable(rv_attr) else (rv_attr or {})
    except Exception:
        return {}

def _deployment_option(raw: Dict[str, Any]) -> str:
    return "Multi-AZ" if _to_bool(raw.get("multi_az", False)) else "Single-AZ"

def _engine_to_database_engine(engine: str) -> Optional[str]:
    """
    Map TF engine -> pricing 'databaseEngine' exactly as in the catalog.
    """
    e = (engine or "").strip().lower()
    if e == "postgres":
        return "PostgreSQL"
    if e == "mysql":
        return "MySQL"
    if e == "mariadb":
        return "MariaDB"
    # Important: Aurora MySQL flavor uses "Amazon Aurora MySQL" in many price lists
    if e in ("aurora", "aurora-mysql"):
        return "Aurora MySQL"   # <- use this exact string
    if e == "aurora-postgresql":
        return "Aurora PostgreSQL"

    if e in ("oracle-se", "oracle-se1", "oracle-se2", "oracle-ee"):
        return "Oracle"
    if e in ("sqlserver-ex", "sqlserver-web", "sqlserver-se", "sqlserver-ee"):
        return "SQL Server"
    return None

def _engine_to_database_edition(engine: str) -> Optional[str]:
    e = (engine or "").strip().lower()
    if e in ("oracle-se", "sqlserver-se"):
        return "Standard"
    if e == "oracle-se1":
        return "Standard One"
    if e == "oracle-se2":
        return "Standard Two"
    if e in ("oracle-ee", "sqlserver-ee"):
        return "Enterprise"
    if e == "sqlserver-ex":
        return "Express"
    if e == "sqlserver-web":
        return "Web"
    return None

def _license_model(engine: str, license_model: str | None) -> Optional[str]:
    e = (engine or "").strip().lower()
    lm = (license_model or "").strip().lower()

    # Go rule 1: engine implies "License included" for oracle-se1, oracle-se2, sqlserver-*
    if e in ("oracle-se1", "oracle-se2") or e.startswith("sqlserver-"):
        implied = "License included"
    else:
        implied = None

    # Go rule 2: override if user explicitly sets BYOL
    if lm == "bring-your-own-license":
        return "Bring your own license"

    return implied

def _volume_type(raw: Dict[str, Any]) -> str:
    """
    Go logic:
      default "General Purpose"
      if iops exists (non-null) -> "Provisioned IOPS"
      else if storage_type == "standard" -> "Magnetic"
      else if storage_type == "io1" -> "Provisioned IOPS"
    """
    storage_type = (raw.get("storage_type") or "").strip().lower()
    iops_present = raw.get("iops", None) is not None

    if iops_present:
        return "Provisioned IOPS"
    if storage_type == "standard":
        return "Magnetic"
    if storage_type == "io1":
        return "Provisioned IOPS"
    return "General Purpose"


# ---------------- price components ----------------

class _RdsInstanceHours(BaseAwsPriceComponent):
    """
    Name:  "Database instance"
    Unit:  hours (qty = 1/hour)
    Service: AmazonRDS
    ProductFamily: Database Instance
    Filters include instanceType, deploymentOption, databaseEngine (+ edition/license when present)
    Purchase option: OnDemand (price-level)
    """
    def __init__(self, resource: "DbInstance"):
        super().__init__(name="Database instance", resource=resource, time_unit="hour")

        rv = _rv_of(resource)
        instance_type = str(rv.get("instance_class", "") or "")
        deployment = _deployment_option(rv)
        db_engine = _engine_to_database_engine(str(rv.get("engine", "") or ""))
        db_edition = _engine_to_database_edition(str(rv.get("engine", "") or ""))
        license_model = _license_model(str(rv.get("engine", "") or ""), rv.get("license_model"))

        # Product-level filters
        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Instance"),
            Filter(key="instanceType", value=instance_type),
            Filter(key="deploymentOption", value=deployment),
        ]
        if db_engine:
            self.default_filters.append(Filter(key="databaseEngine", value=db_engine))
        if db_edition:
            self.default_filters.append(Filter(key="databaseEdition", value=db_edition))
        if license_model:
            self.default_filters.append(Filter(key="licenseModel", value=license_model))

        # Purchase term belongs at the PRICE level
        self.set_price_filter({"purchaseOption": "on_demand", "unit": "Hrs"})

        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))
        self.unit_ = "hours"


class _RdsStorage(BaseAwsPriceComponent):
    """
    Name:  "Database storage"
    Unit:  GB-months
    Service: AmazonRDS
    ProductFamily: Database Storage
    Filters: volumeType, deploymentOption
    Quantity: allocated_storage (monthly GB)
    """
    def __init__(self, resource: "DbInstance"):
        super().__init__(name="Database storage", resource=resource, time_unit="month")

        rv = _rv_of(resource)
        deployment = _deployment_option(rv)
        volume_type = _volume_type(rv)

        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Database Storage"),
            Filter(key="volumeType", value=volume_type),
            Filter(key="deploymentOption", value=deployment),
        ]

        allocated = _to_decimal(rv.get("allocated_storage"))
        self.SetQuantityMultiplierFunc(lambda _r: allocated)
        self.unit_ = "GB-months"


class _RdsStorageIops(BaseAwsPriceComponent):
    """
    Name:  "Database storage IOPS"
    Unit:  IOPS-months
    Service: AmazonRDS
    ProductFamily: Provisioned IOPS
    Filters: deploymentOption
    Quantity: iops (monthly)
    Only added when volumeType == "Provisioned IOPS".
    """
    def __init__(self, resource: "DbInstance"):
        super().__init__(name="Database storage IOPS", resource=resource, time_unit="month")

        rv = _rv_of(resource)
        deployment = _deployment_option(rv)

        self.default_filters = [
            Filter(key="servicecode", value="AmazonRDS"),
            Filter(key="productFamily", value="Provisioned IOPS"),
            Filter(key="deploymentOption", value=deployment),
        ]

        iops = _to_decimal(rv.get("iops"))
        self.SetQuantityMultiplierFunc(lambda _r: iops)
        self.unit_ = "IOPS-months"


# ---------------- resource ----------------

class DbInstance(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/db_instance.go::NewDBInstance

    Components:
      - "Database instance"         (hours, qty=1)
      - "Database storage"          (GB-months, qty=allocated_storage)
      - "Database storage IOPS"     (IOPS-months, qty=iops)  — only for Provisioned IOPS
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)

        rv = raw_values or {}
        components = [
            _RdsInstanceHours(self),
            _RdsStorage(self),
        ]

        if _volume_type(rv) == "Provisioned IOPS":
            components.append(_RdsStorageIops(self))

        self._set_price_components(components)


# Optional aliases if your registry uses different names
RdsInstance = DbInstance
AwsDbInstance = DbInstance
