# plancosts/plancosts/providers/terraform/aws/ecs_service.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsResource, BaseAwsPriceComponent


# Region → usagetype prefix used by AWS billing (extend as needed)
_REGION_PREFIX = {
    "us-east-1": "USE1-",
    "us-east-2": "USE2-",
    "us-west-1": "USW1-",
    "us-west-2": "USW2-",
}


def _prefix(region: str) -> str:
    return _REGION_PREFIX.get(region, "")


def _to_decimal(v: Any, default: Decimal = Decimal(0)) -> Decimal:
    if v is None:
        return default
    try:
        return Decimal(str(v))
    except Exception:
        return default


def _parse_cpu(cpu_field: Any) -> Decimal:
    # Accept: "1 vCPU", "0.25 vCPU", 1, "1"
    if cpu_field is None:
        return Decimal(0)
    if isinstance(cpu_field, (int, float, Decimal)):
        return _to_decimal(cpu_field)
    s = str(cpu_field).strip().replace(" vCPU", "").replace("vCPU", "").strip()
    return _to_decimal(s)


def _parse_memory_gb(mem_field: Any) -> Decimal:
    # Accept: "2 GB", 2, "2"
    if mem_field is None:
        return Decimal(0)
    if isinstance(mem_field, (int, float, Decimal)):
        return _to_decimal(mem_field)
    s = str(mem_field).strip().replace(" GB", "").replace("GB", "").strip()
    return _to_decimal(s)


class _FargateMemoryGBHours(BaseAwsPriceComponent):
    """Fargate Memory cost (GB-hours)."""

    def __init__(self, resource: "EcsService"):
        super().__init__(name="GB hours", resource=resource, time_unit="hour")
        # Example usagetype: USE1-Fargate-GB-Hours
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value=f"{_prefix(resource.region())}Fargate-GB-Hours"),
        ]
        # Quantity is set by the resource via SetQuantityMultiplierFunc
        self.SetQuantityMultiplierFunc(lambda r: r._qty_mem_gb_hours())  # type: ignore[attr-defined]
        self.unit_ = "hour"


class _FargateCPUHours(BaseAwsPriceComponent):
    """Fargate CPU cost (vCPU-hours)."""

    def __init__(self, resource: "EcsService"):
        super().__init__(name="CPU hours", resource=resource, time_unit="hour")
        # Example usagetype: USE1-Fargate-vCPU-Hours:perCPU
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value=f"{_prefix(resource.region())}Fargate-vCPU-Hours:perCPU"),
        ]
        self.SetQuantityMultiplierFunc(lambda r: r._qty_cpu_hours())  # type: ignore[attr-defined]
        self.unit_ = "hour"


class _FargateEphemeralGBHours(BaseAwsPriceComponent):
    """Fargate Ephemeral Storage (GB-hours). Only added if size detected."""

    def __init__(self, resource: "EcsService"):
        super().__init__(name="Ephemeral storage GB hours", resource=resource, time_unit="hour")
        # Example usagetype: USE1-Fargate-EphemeralStorage-GB-Hours
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value=f"{_prefix(resource.region())}Fargate-EphemeralStorage-GB-Hours"),
        ]
        self.SetQuantityMultiplierFunc(lambda r: r._qty_ephemeral_gb_hours())  # type: ignore[attr-defined]
        self.unit_ = "hour"


class EcsService(BaseAwsResource):
    """
    AWS ECS Fargate Service.

    We read CPU/Memory (and optional ephemeral storage / EI) from the linked
    aws_ecs_task_definition (wired as a reference by the Terraform parser).
    """

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)

        pcs: List[BaseAwsPriceComponent] = [
            _FargateMemoryGBHours(self),
            _FargateCPUHours(self),
        ]

        # Add Ephemeral storage line only if a size is present in the task def
        if self._ephemeral_storage_gb() > 0:
            pcs.append(_FargateEphemeralGBHours(self))

        self._set_price_components(pcs)

    # ---------- quantities (evaluated at pricing time) ----------

    def _desired_count(self) -> Decimal:
        try:
            return _to_decimal(self.raw_values().get("desired_count", 1), Decimal(1))
        except Exception:
            return Decimal(1)

    def _taskdef_resource(self) -> Optional[BaseAwsResource]:
        # The parser wires references via add_reference(key, resource).
        # Try several common shapes to be safe.
        for attr in ("references", "refs", "_refs", "_references"):
            refs = getattr(self, attr, None)
            if callable(refs):
                try:
                    refs = refs()
                except Exception:
                    pass
            if isinstance(refs, dict):
                # Prefer explicit key
                if "task_definition" in refs:
                    return refs["task_definition"]  # type: ignore[return-value]
                # Fallback: any aws_ecs_task_definition
                for v in refs.values():
                    try:
                        if hasattr(v, "address") and "aws_ecs_task_definition" in v.address():
                            return v  # type: ignore[return-value]
                    except Exception:
                        continue
        return None

    def _taskdef_raw(self) -> Dict[str, Any]:
        td = self._taskdef_resource()
        if td is None:
            return {}
        # Try common ways to get raw dict
        for getter in ("raw_values", "raw"):
            rv = getattr(td, getter, None)
            if callable(rv):
                try:
                    val = rv()
                    if isinstance(val, dict):
                        return val
                except Exception:
                    pass
        for attr in ("raw_values", "raw", "_raw"):
            val = getattr(td, attr, None)
            if isinstance(val, dict):
                return val
        return {}

    def _memory_gb(self) -> Decimal:
        return _parse_memory_gb(self._taskdef_raw().get("memory"))

    def _vcpu(self) -> Decimal:
        return _parse_cpu(self._taskdef_raw().get("cpu"))

    def _ephemeral_storage_gb(self) -> Decimal:
        es = self._taskdef_raw().get("ephemeral_storage")
        if isinstance(es, dict) and es.get("size") is not None:
            return _to_decimal(es.get("size"), Decimal(0))
        if isinstance(es, (int, float, Decimal, str)):
            return _to_decimal(es, Decimal(0))
        return Decimal(0)

    # Multipliers used by price components
    def _qty_mem_gb_hours(self) -> Decimal:
        return self._memory_gb() * self._desired_count()

    def _qty_cpu_hours(self) -> Decimal:
        return self._vcpu() * self._desired_count()

    def _qty_ephemeral_gb_hours(self) -> Decimal:
        return self._ephemeral_storage_gb() * self._desired_count()
