# plancosts/providers/terraform/aws/lambda_function.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Dict, Optional

from plancosts.resource.filters import Filter
from .base import BaseAwsPriceComponent, BaseAwsResource


# ---------------- helpers ----------------

def _D(x: Any, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _safe_call_or_value(obj: Any) -> Any:
    """Return obj() if callable, else obj; swallow exceptions and return {}."""
    if callable(obj):
        try:
            return obj()
        except Exception:
            return {}
    return obj


def _raw_dict(resource: BaseAwsResource) -> Dict[str, Any]:
    """
    Return the resource's raw values as a dict regardless of whether
    it's exposed as a method (raw_values()) or an attribute (raw_values).
    """
    raw = getattr(resource, "raw_values", {})  # method or dict
    raw = _safe_call_or_value(raw)
    return raw or {}


def _usage_map(resource: BaseAwsResource) -> Dict[str, Any]:
    """
    Return the usage dict from either resource.usage_values (method/attr)
    or raw_values().get('usage', {}).
    """
    # Preferred: explicit usage_values
    if hasattr(resource, "usage_values"):
        u = getattr(resource, "usage_values")
        u = _safe_call_or_value(u)
        if isinstance(u, dict) and u:
            return u

    # Fallback: nested in raw_values
    raw = _raw_dict(resource)
    usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
    return usage or {}


def _usage_value(resource: BaseAwsResource, key: str) -> Optional[Any]:
    """
    Get a usage value by key, tolerant of either storage shape.
    """
    usage = _usage_map(resource)
    if key in usage:
        return usage[key]
    return None


def _usage_number(resource: BaseAwsResource, key: str, default: Decimal = Decimal(0)) -> Decimal:
    """
    Extract a numeric usage value from common shapes:
      - number (123)
      - string ("123")
      - dict {"value": 123}
      - list [{"value": 123}] or [123]
    """
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
    """
    Like _usage_number but returns None if the key is absent/unreadable.
    """
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
    """
    Default 128 MB unless 'memory_size' is specified.
    Accepts dict-like; callers pass _raw_dict(resource).
    """
    if isinstance(raw, dict) and raw.get("memory_size") is not None:
        return _D(raw["memory_size"], Decimal(128))
    return Decimal(128)


def _gb_seconds(memory_mb: Decimal, request_duration_ms: Decimal, monthly_requests: Decimal) -> Decimal:
    """
    Port calculateGBSeconds:

      gb := memorySize / 1024
      seconds := ceil(requestDuration / 100) * 0.1   # round up to nearest 100ms, then to seconds
      return monthlyRequests * gb * seconds
    """
    if monthly_requests <= 0:
        return Decimal(0)

    gb = (memory_mb / Decimal(1024)) if memory_mb > 0 else Decimal(0)

    # Round up to the nearest 100ms bin:
    hundred_ms_bins = (request_duration_ms / Decimal(100)).to_integral_value(rounding=ROUND_CEILING)
    seconds_per_request = hundred_ms_bins * Decimal("0.1")

    return monthly_requests * gb * seconds_per_request


# ---------------- price components ----------------

class _LambdaRequests(BaseAwsPriceComponent):
    """
    Name:  "Requests"
    Unit:  "requests" (monthly)
    Service: AWSLambda
    ProductFamily: Serverless
    Quantity: monthly_requests usage (default 0)
    """
    def __init__(self, r: "LambdaFunction"):
        super().__init__(name="Requests", resource=r, time_unit="month")
        # Disambiguate by group to get the canonical Requests SKU.
        self.default_filters = [
            Filter(key="servicecode", value="AWSLambda"),
            Filter(key="productFamily", value="Serverless"),
            Filter(key="group", value="AWS-Lambda-Requests"),
        ]
        # Exact unit used by catalog
        self.set_price_filter({
            "unit": "Requests",
            "purchaseOption": "on_demand",
        })
        self.unit_ = "requests"
        self.SetQuantityMultiplierFunc(lambda res: _usage_number(res, "monthly_requests", Decimal(0)))


class _LambdaDuration(BaseAwsPriceComponent):
    """
    Name:  "Duration"
    Unit:  "GB-seconds" (monthly)
    Service: AWSLambda
    ProductFamily: Serverless

    Quantity:
      ceil(duration_ms / 100) * 0.1 * (memory_mb / 1024) * monthly_requests
    Accepts usage key "average_request_duration" (preferred) or "request_duration".
    """
    def __init__(self, r: "LambdaFunction"):
        super().__init__(name="Duration", resource=r, time_unit="month")
        # Disambiguate by group to get the canonical Duration SKU.
        self.default_filters = [
            Filter(key="servicecode", value="AWSLambda"),
            Filter(key="productFamily", value="Serverless"),
            Filter(key="group", value="AWS-Lambda-Duration"),
        ]
        # Your catalog exposes Duration as unit = "seconds" (tiered), with purchaseOption present.
        self.set_price_filter({
            "unit": "seconds",
            "purchaseOption": "on_demand",
            # Optional: tighten if needed
            # "descriptionRegex": ".*Total Compute.*",
        })
        self.unit_ = "GB-seconds"

        def _qty(res: "LambdaFunction") -> Decimal:
            raw = _raw_dict(res)
            mem_mb = _memory_size_mb(raw)
            monthly_requests = _usage_number(res, "monthly_requests", Decimal(0))

            # Prefer "average_request_duration", fall back to "request_duration"
            dur_ms_opt = _usage_number_optional(res, "average_request_duration")
            if dur_ms_opt is None:
                dur_ms = _usage_number(res, "request_duration", Decimal(0))
            else:
                dur_ms = dur_ms_opt

            return _gb_seconds(mem_mb, dur_ms, monthly_requests)

        self.SetQuantityMultiplierFunc(_qty)


# ---------------- resource ----------------

class LambdaFunction(BaseAwsResource):
    """
    Python port of internal/providers/terraform/aws/lambda_function::NewLambdaFunction

    Cost components:
      - Requests        (monthly, unit "requests")
      - Duration        (monthly, unit "GB-seconds")
    """
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        self._set_price_components([
            _LambdaRequests(self),
            _LambdaDuration(self),
        ])


NewLambdaFunction = LambdaFunction
AwsLambdaFunction = LambdaFunction
