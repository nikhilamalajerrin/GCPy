# plancosts/providers/terraform/aws/lambda_function.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Dict, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


def _D(x: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _safe_call_or_value(obj: Any) -> Any:
    if callable(obj):
        try:
            return obj()
        except Exception:
            return {}
    return obj


def _raw_dict(resource: BaseAwsResource) -> Dict[str, Any]:
    raw = getattr(resource, "raw_values", {})
    raw = _safe_call_or_value(raw)
    return raw or {}


def _usage_map(resource: BaseAwsResource) -> Dict[str, Any]:
    if hasattr(resource, "usage_values"):
        u = getattr(resource, "usage_values")
        u = _safe_call_or_value(u)
        if isinstance(u, dict) and u:
            return u
    raw = _raw_dict(resource)
    usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
    return usage or {}


def _usage_value(resource: BaseAwsResource, key: str) -> Optional[Any]:
    usage = _usage_map(resource)
    if key in usage:
        return usage[key]
    return None


def _usage_number(resource: BaseAwsResource, key: str, default: Decimal = Decimal(0)) -> Decimal:
    v = _usage_value(resource, key)
    if v is None:
        return default
    if isinstance(v, (int, float, Decimal, str)):
        return _D(v, default)
    if isinstance(v, dict) and "value" in v:
        return _D(v.get("value"), default)
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict) and "value" in first:
            return _D(first.get("value"), default)
        return _D(first, default)
    return default


def _usage_number_optional(resource: BaseAwsResource, key: str) -> Optional[Decimal]:
    v = _usage_value(resource, key)
    if v is None:
        return None
    try:
        if isinstance(v, (int, float, Decimal, str)):
            return _D(v, None)  # type: ignore[arg-type]
        if isinstance(v, dict) and "value" in v:
            return _D(v.get("value"), None)  # type: ignore[arg-type]
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, dict) and "value" in first:
                return _D(first.get("value"), None)  # type: ignore[arg-type]
            return _D(first, None)  # type: ignore[arg-type]
    except Exception:
        return None
    return None


def _memory_size_mb(raw: Dict[str, Any]) -> Decimal:
    if isinstance(raw, dict) and raw.get("memory_size") is not None:
        return _D(raw["memory_size"], Decimal(128))
    return Decimal(128)


def _gb_seconds(memory_mb: Decimal, request_duration_ms: Decimal, monthly_requests: Decimal) -> Decimal:
    if monthly_requests <= 0:
        return Decimal(0)
    gb = (memory_mb / Decimal(1024)) if memory_mb > 0 else Decimal(0)
    hundred_ms_bins = (request_duration_ms / Decimal(100)).to_integral_value(rounding=ROUND_CEILING)
    seconds_per_request = hundred_ms_bins * Decimal("0.1")
    return monthly_requests * gb * seconds_per_request


class _LambdaRequests(BaseAwsPriceComponent):
    def __init__(self, r: "LambdaFunction"):
        super().__init__(name="Requests", resource=r, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AWSLambda"),
            Filter(key="productFamily", value="Serverless"),
            Filter(key="group", value="AWS-Lambda-Requests"),
        ]
        self.set_price_filter({
            "unit": "Requests",
            "purchaseOption": "on_demand",
        })
        self.unit_ = "requests"
        self.SetQuantityMultiplierFunc(lambda res: _usage_number(res, "monthly_requests", Decimal(0)))


class _LambdaDuration(BaseAwsPriceComponent):
    def __init__(self, r: "LambdaFunction"):
        super().__init__(name="Duration", resource=r, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AWSLambda"),
            Filter(key="productFamily", value="Serverless"),
            Filter(key="group", value="AWS-Lambda-Duration"),
        ]
        self.set_price_filter({
            "unit": "seconds",
            "purchaseOption": "on_demand",
        })
        self.unit_ = "GB-seconds"

        def _qty(res: "LambdaFunction") -> Decimal:
            raw = _raw_dict(res)
            mem_mb = _memory_size_mb(raw)
            monthly_requests = _usage_number(res, "monthly_requests", Decimal(0))
            dur_ms_opt = _usage_number_optional(res, "average_request_duration")
            dur_ms = dur_ms_opt if dur_ms_opt is not None else _usage_number(res, "request_duration", Decimal(0))
            return _gb_seconds(mem_mb, dur_ms, monthly_requests)

        self.SetQuantityMultiplierFunc(_qty)


class LambdaFunction(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([
            _LambdaRequests(self),
            _LambdaDuration(self),
        ])


NewLambdaFunction = LambdaFunction
AwsLambdaFunction = LambdaFunction
