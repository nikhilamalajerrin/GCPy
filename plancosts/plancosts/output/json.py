# plancosts/output/json.py
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Dict, List


# ---- rounding helpers (match Go: Round(6) -> banker's rounding) ----

_D6 = Decimal("0.000001")

def _to_decimal(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)

def _round6(v: Any) -> Decimal:
    # shopspring/decimal Round(6) uses banker's rounding; map to HALF_EVEN
    return _to_decimal(v).quantize(_D6, rounding=ROUND_HALF_EVEN)

def _num(v: Any) -> float:
    """Convert to a JSON-safe number (float) after rounding to 6 dp."""
    return float(_round6(v))


# ---- schema accessors (duck-typed to tolerate minor diffs) ----

def _name(resource) -> str:
    for attr in ("Name", "name"):
        if hasattr(resource, attr):
            val = getattr(resource, attr)
            return val() if callable(val) else val
    if hasattr(resource, "Address") and callable(getattr(resource, "Address")):
        return str(resource.Address())
    return "<resource>"

def _hourly_cost(resource) -> Decimal:
    fn = getattr(resource, "HourlyCost", None)
    return _to_decimal(fn()) if callable(fn) else Decimal(0)

def _monthly_cost(resource) -> Decimal:
    fn = getattr(resource, "MonthlyCost", None)
    return _to_decimal(fn()) if callable(fn) else Decimal(0)

def _cost_components(resource) -> List[Any]:
    for attr in ("CostComponents", "cost_components"):
        v = getattr(resource, attr, None)
        if callable(v):
            try:
                v = v()
            except Exception:
                v = None
        if isinstance(v, list):
            return v
    return []

def _subresources(resource) -> List[Any]:
    for attr in ("SubResources", "sub_resources"):
        v = getattr(resource, attr, None)
        if callable(v):
            try:
                v = v()
            except Exception:
                v = None
        if isinstance(v, list):
            return v
    return []


# ---- cost component accessors ----

def _cc_name(cc) -> str:
    for attr in ("Name", "name"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return str(v())
            except Exception:
                continue
        if isinstance(v, str):
            return v
    return "<component>"

def _cc_unit(cc) -> str:
    for attr in ("Unit", "unit"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return str(v())
            except Exception:
                continue
        if isinstance(v, str):
            return v
    return ""

def _cc_hourly_qty(cc) -> Decimal:
    for attr in ("HourlyQuantity", "hourly_quantity"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return _to_decimal(v())
            except Exception:
                continue
    return Decimal(0)

def _cc_monthly_qty(cc) -> Decimal:
    for attr in ("MonthlyQuantity", "monthly_quantity"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return _to_decimal(v())
            except Exception:
                continue
    return Decimal(0)

def _cc_price(cc) -> Decimal:
    for attr in ("Price", "price"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return _to_decimal(v())
            except Exception:
                continue
    return Decimal(0)

def _cc_hourly_cost(cc) -> Decimal:
    for attr in ("HourlyCost", "hourly_cost"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return _to_decimal(v())
            except Exception:
                continue
    return Decimal(0)

def _cc_monthly_cost(cc) -> Decimal:
    for attr in ("MonthlyCost", "monthly_cost"):
        v = getattr(cc, attr, None)
        if callable(v):
            try:
                return _to_decimal(v())
            except Exception:
                continue
    return Decimal(0)


# ---- builders (mirror Go structs/tags) ----

def _new_cost_component_json(cc) -> Dict[str, Any]:
    return {
        "name":            _cc_name(cc),
        "unit":            _cc_unit(cc),
        "hourlyQuantity":  _num(_cc_hourly_qty(cc)),
        "monthlyQuantity": _num(_cc_monthly_qty(cc)),
        "price":           _num(_cc_price(cc)),
        "hourlyCost":      _num(_cc_hourly_cost(cc)),
        "monthlyCost":     _num(_cc_monthly_cost(cc)),
    }

def _new_resource_json(resource) -> Dict[str, Any]:
    cc_list = [_new_cost_component_json(cc) for cc in _cost_components(resource)]
    sub_list = [_new_resource_json(sr) for sr in _subresources(resource)]

    out: Dict[str, Any] = {
        "name":        _name(resource),
        "hourlyCost":  _num(_hourly_cost(resource)),
        "monthlyCost": _num(_monthly_cost(resource)),
    }
    if cc_list:
        out["costComponents"] = cc_list
    if sub_list:
        out["subresources"] = sub_list
    return out


# ---- public API ----

def to_json(resources: List[Any], pretty: bool = False) -> bytes:
    """
    Return a JSON byte string equivalent to Go's output.ToJSON.
    - Rounds all numeric fields to 6 decimal places, banker's rounding.
    - Omits empty arrays for costComponents/subresources (like omitempty).
    """
    payload = [_new_resource_json(r) for r in resources]
    if pretty:
        return json.dumps(payload, indent=2, separators=(", ", ": ")).encode("utf-8")
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


# Optional alias to mirror Go naming at call sites, if desired.
ToJSON = to_json
