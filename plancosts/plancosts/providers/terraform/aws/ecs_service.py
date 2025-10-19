from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource

if TYPE_CHECKING:
    # Only for static type checking; not imported at runtime (avoids cycles).
    from plancosts.schema.resource_data import ResourceData

log = logging.getLogger(__name__)


def _to_decimal(s: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _convert_resource_string(raw: str) -> Decimal:
    """
    Port of convertResourceString:

    - Trim whitespace
    - Case-insensitive handling of "GB" and "vCPU" suffixes
    - If a unit suffix is present, strip it and parse the remaining number
    - Otherwise, treat the value as MiB and convert to GiB by dividing by 1024
    """
    if not isinstance(raw, str):
        return Decimal(0)

    s = raw.strip().replace(" ", "")
    if not s:
        return Decimal(0)

    lower = s.lower()

    # Handle GB / vCPU units case-insensitively
    if "gb" in lower or "vcpu" in lower:
        # Normalize to lower case so mixed case like "Gb" or "vCPU" works
        numeric = lower.replace("gb", "").replace("vcpu", "")
        return _to_decimal(numeric, Decimal(0))

    # No explicit unit: interpret as MiB and convert to GiB
    val = _to_decimal(lower, Decimal(0))
    if val == 0:
        return val
    return val / Decimal(1024)


def _safe_raw_values(obj: Any) -> Dict[str, Any]:
    """
    Return a plain dict for ResourceData.raw_values (callable/dict) or dicts.
    """
    try:
        vals = getattr(obj, "raw_values", obj)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}


def _extract_inference_device_type(td: "ResourceData") -> Optional[str]:
    """
    Try multiple ways to get task definition's inference accelerator device_type.
    Priority:
      1) td.Get("inference_accelerator.0.device_type").String() if available
      2) td.raw_values()["inference_accelerator"][0]["device_type"] if present
    """
    # 1) Structured accessor path (works when schema helpers exist)
    try:
        getter = getattr(td, "Get", None)
        if callable(getter):
            s_method = getter("inference_accelerator.0.device_type")
            str_method = getattr(s_method, "String", None)
            if callable(str_method):
                v = str_method()
                if v:
                    return str(v)
    except Exception:
        pass

    # 2) Raw values fallback (handles simple dict-based ResourceData)
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


class _FargateGBHours(BaseAwsPriceComponent):
    """
    Name: "Per GB per hour"
    Unit: "GB-hours"
    Hourly quantity: desired_count * memory(GB)
    Product match:
      - servicecode: AmazonECS
      - productFamily: Compute
      - usagetype ~= /(Fargate-GB-(Hours|Seconds))/
    """
    def __init__(self, r: "EcsService", desired_count: int, memory_gb: Decimal):
        super().__init__("Per GB per hour", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value="/Fargate-GB-(Hours|Seconds)/", operation="REGEX"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "GB-hours"
        qty = (Decimal(desired_count) * memory_gb)
        self.SetQuantityMultiplierFunc(lambda _r: qty)


class _FargateVCPUHours(BaseAwsPriceComponent):
    """
    Name: "Per vCPU per hour"
    Unit: "CPU-hours"
    Hourly quantity: desired_count * vcpu
    Product match:
      - servicecode: AmazonECS
      - productFamily: Compute
      - usagetype ~= /(Fargate-vCPU-(Hours|Seconds)(:perCPU)?)/ 
    """
    def __init__(self, r: "EcsService", desired_count: int, vcpu: Decimal):
        super().__init__("Per vCPU per hour", r, "hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonECS"),
            Filter(key="productFamily", value="Compute"),
            Filter(key="usagetype", value="/Fargate-vCPU-(Hours|Seconds)(:perCPU)?/", operation="REGEX"),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "CPU-hours"
        qty = (Decimal(desired_count) * vcpu)
        self.SetQuantityMultiplierFunc(lambda _r: qty)


class _ElasticInferenceHours(BaseAwsPriceComponent):
    """
    Name: "Inference accelerator (<device_type>)"
    Unit: "hours"
    Hourly quantity: desired_count
    Product match:
      - servicecode: AmazonEI
      - productFamily: Elastic Inference
      - usagetype includes device_type (regex)
    """
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


class EcsService(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/ecs_service

    Only prices launch_type == "FARGATE".
    Reads task_definition (cpu/memory and optional inference accelerator) from
    ResourceData references if available
    """
    def __init__(
        self,
        address: str,
        region: str,
        raw_values: Dict[str, Any],
        rd: Optional["ResourceData"] = None,  # pass ResourceData so we can inspect refs
    ):
        super().__init__(address, region, raw_values)

        # Not Fargate? Log a warning and return no components.
        launch_type = str(raw_values.get("launch_type") or "")
        if launch_type != "FARGATE":
            log.warning(
                "Unsupported launch type for aws_ecs_service. Currently only FARGATE is supported"
            )
            self._set_price_components([])
            return

        desired_count = int(raw_values.get("desired_count") or 0)

        # Resolve task_definition via references
        memory_raw: Optional[str] = None
        cpu_raw: Optional[str] = None
        accel_device_type: Optional[str] = None

        if rd is not None:
            refs = rd.References("task_definition") or []
            if refs:
                td = refs[0]
                # Try structured getters first
                try:
                    memory_raw = td.Get("memory").String()
                except Exception:
                    memory_raw = None
                try:
                    cpu_raw = td.Get("cpu").String()
                except Exception:
                    cpu_raw = None
                # Accelerator via robust extractor
                accel_device_type = _extract_inference_device_type(td) or None

        # Fallbacks (if flattened elsewhere)
        if memory_raw is None:
            memory_raw = str(raw_values.get("task_definition.memory") or "")
        if cpu_raw is None:
            cpu_raw = str(raw_values.get("task_definition.cpu") or "")

        mem_gb = _convert_resource_string(memory_raw or "0")
        vcpu = _convert_resource_string(cpu_raw or "0")

        pcs: List[BaseAwsPriceComponent] = []
        pcs.append(_FargateGBHours(self, desired_count, mem_gb))
        pcs.append(_FargateVCPUHours(self, desired_count, vcpu))

        if accel_device_type:
            pcs.append(_ElasticInferenceHours(self, desired_count, accel_device_type))

        self._set_price_components(pcs)



AwsEcsService = EcsService
NewEcsService = EcsService
