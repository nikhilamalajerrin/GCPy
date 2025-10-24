# plancosts/providers/terraform/aws/ecs_service.py
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource

if TYPE_CHECKING:
    from plancosts.schema.resource_data import ResourceData

log = logging.getLogger(__name__)


def _to_decimal(s: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _convert_resource_string(raw: str) -> Decimal:
    if not isinstance(raw, str):
        return Decimal(0)
    s = raw.strip().replace(" ", "")
    if not s:
        return Decimal(0)
    lower = s.lower()
    if "gb" in lower or "vcpu" in lower:
        numeric = lower.replace("gb", "").replace("vcpu", "")
        return _to_decimal(numeric, Decimal(0))
    val = _to_decimal(lower, Decimal(0))
    if val == 0:
        return val
    return val / Decimal(1024)


def _safe_raw_values(obj: Any) -> Dict[str, Any]:
    try:
        vals = getattr(obj, "raw_values", obj)
        if callable(vals):
            vals = vals() or {}
        return dict(vals or {})
    except Exception:
        return {}


def _extract_inference_device_type(td: "ResourceData") -> Optional[str]:
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


class EcsService(BaseAwsResource):
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

        if rd is not None:
            refs = rd.References("task_definition") or []
            if refs:
                td = refs[0]
                try:
                    memory_raw = td.Get("memory").String()
                except Exception:
                    memory_raw = None
                try:
                    cpu_raw = td.Get("cpu").String()
                except Exception:
                    cpu_raw = None
                accel_device_type = _extract_inference_device_type(td) or None

        if memory_raw is None:
            memory_raw = str(raw_values.get("task_definition.memory") or "")
        if cpu_raw is None:
            cpu_raw = str(raw_values.get("task_definition.cpu") or "")

        mem_gb = _convert_resource_string(memory_raw or "0")
        vcpu = _convert_resource_string(cpu_raw or "0")

        pcs: List[BaseAwsPriceComponent] = [
            _FargateGBHours(self, desired_count, mem_gb),
            _FargateVCPUHours(self, desired_count, vcpu),
        ]
        if accel_device_type:
            pcs.append(_ElasticInferenceHours(self, desired_count, accel_device_type))

        self._set_price_components(pcs)


AwsEcsService = EcsService
NewEcsService = EcsService
