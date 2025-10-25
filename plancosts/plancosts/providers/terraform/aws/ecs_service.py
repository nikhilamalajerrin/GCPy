from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource

if TYPE_CHECKING:
    from plancosts.schema.resource_data import ResourceData

log = logging.getLogger(__name__)


# ---------- Utility functions ----------

def _to_decimal(s: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Convert safely to Decimal, returning a default on error."""
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _convert_resource_string(raw: str) -> Decimal:
    """
    Mirrors convertResourceString in Go.
    - Handles strings like "512" (MB) → 0.5 GB
    - Handles "0.25 vCPU", "1 GB", etc.
    """
    if not isinstance(raw, str):
        return Decimal(0)
    s = raw.strip().replace(" ", "")
    if not s:
        return Decimal(0)

    # Case-insensitive regex match for vCPU or GB
    if re.search(r"(?i)(vcpu|gb)", s):
        numeric = re.sub(r"(?i)(vcpu|gb)", "", s)
        return _to_decimal(numeric, Decimal(0))
    else:
        val = _to_decimal(s, Decimal(0))
        if val == 0:
            return val
        # Interpret as MB → convert to GB
        return val / Decimal(1024)


def _safe_raw_values(obj: Any) -> Dict[str, Any]:
    """Safely unwrap .raw_values() or return as dict."""
    try:
        vals = getattr(obj, "raw_values", obj)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}


def _extract_inference_device_type(td: "ResourceData") -> Optional[str]:
    """Mirror Go: taskDefinition.Get('inference_accelerator.0.device_type').String()"""
    try:
        getter = getattr(td, "Get", None)
        if callable(getter):
            s_method = getter("inference_accelerator.0.device_type")
            str_method = getattr(s_method, "String", None)
            if callable(str_method):
                val = str_method()
                if val:
                    return str(val)
    except Exception:
        pass
    try:
        rv = _safe_raw_values(td)
        accels = rv.get("inference_accelerator")
        if isinstance(accels, list) and accels:
            first = accels[0] or {}
            dt = first.get("device_type")
            if dt:
                return str(dt)
    except Exception:
        pass
    return None


# ---------- Price components ----------

class _FargateGBHours(BaseAwsPriceComponent):
    def __init__(self, r: "EcsService", desired_count: int, memory_gb: Decimal):
        super().__init__("Per GB per hour", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value="/Fargate-GB-(Hours|Seconds)/", operation="REGEX"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "GB-hours"
        qty = Decimal(desired_count) * memory_gb
        self.SetQuantityMultiplierFunc(lambda _r: qty)


class _FargateVCPUHours(BaseAwsPriceComponent):
    def __init__(self, r: "EcsService", desired_count: int, vcpu: Decimal):
        super().__init__("Per vCPU per hour", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value="/Fargate-vCPU-(Hours|Seconds)(:perCPU)?/", operation="REGEX"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "CPU-hours"
        qty = Decimal(desired_count) * vcpu
        self.SetQuantityMultiplierFunc(lambda _r: qty)


class _ElasticInferenceHours(BaseAwsPriceComponent):
    def __init__(self, r: "EcsService", desired_count: int, device_type: str):
        super().__init__(f"Inference accelerator ({device_type})", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEI"),
            Filter(key="productFamily", value="Elastic Inference"),
            Filter(key="usagetype", value=f"/{device_type}/", operation="REGEX"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "hours"
        qty = Decimal(desired_count)
        self.SetQuantityMultiplierFunc(lambda _r: qty)


# ---------- ECS Service Resource ----------

class EcsService(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/ecs_service.go::NewECSService

    Supports only Fargate launch type.
    Components:
      - Per GB per hour (AmazonECS)
      - Per vCPU per hour (AmazonECS)
      - Inference accelerator (AmazonEI) [optional]
    """
    def __init__(
        self,
        address: str,
        region: str,
        raw_values: Dict[str, Any],
        rd: Optional["ResourceData"] = None,
    ):
        super().__init__(address, region, raw_values)

        launch_type = str(raw_values.get("launch_type") or "")
        if launch_type != "FARGATE":
            log.warning("Skipping ECS Service: only FARGATE launch type supported")
            self._set_price_components([])
            return

        desired_count = int(raw_values.get("desired_count") or 0)
        memory_raw: Optional[str] = None
        cpu_raw: Optional[str] = None
        accel_device_type: Optional[str] = None

        # Resolve task_definition reference fields
        if rd is not None:
            refs = rd.References("task_definition") or []
            if refs:
                td = refs[0]
                try:
                    memory_raw = td.Get("memory").String()
                except Exception:
                    pass
                try:
                    cpu_raw = td.Get("cpu").String()
                except Exception:
                    pass
                accel_device_type = _extract_inference_device_type(td)

        # fallback from raw_values
        memory_raw = memory_raw or str(raw_values.get("task_definition.memory") or "")
        cpu_raw = cpu_raw or str(raw_values.get("task_definition.cpu") or "")

        mem_gb = _convert_resource_string(memory_raw or "0")
        vcpu = _convert_resource_string(cpu_raw or "0")

        pcs: List[BaseAwsPriceComponent] = [
            _FargateGBHours(self, desired_count, mem_gb),
            _FargateVCPUHours(self, desired_count, vcpu),
        ]

        if accel_device_type:
            pcs.append(_ElasticInferenceHours(self, desired_count, accel_device_type))

        self._set_price_components(pcs)


# Registry aliases (match Infracost convention)
AwsEcsService = EcsService
NewEcsService = EcsService
