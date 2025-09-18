"""
JSON output formatter for cost breakdowns (supports subresources).
"""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

from plancosts.base.costs import ResourceCostBreakdown


def _to_decimal(val) -> Decimal:
    return val if isinstance(val, Decimal) else Decimal(str(val))


def _round6_number(val) -> float:
    d = _to_decimal(val)
    q = Decimal("0.000001")
    return float(d.quantize(q, rounding=ROUND_HALF_UP))


def _create_json_obj(breakdown: ResourceCostBreakdown) -> Dict[str, Any]:
    pcs = [
        {
            "priceComponent": pc_cost.price_component.name(),
            "hourlyCost": _round6_number(pc_cost.hourly_cost),
            "monthlyCost": _round6_number(pc_cost.monthly_cost),
        }
        for pc_cost in breakdown.price_component_costs
    ]
    sub = [_create_json_obj(s) for s in getattr(breakdown, "sub_resource_costs", []) or []]
    obj: Dict[str, Any] = {"resource": breakdown.resource.address(), "breakdown": pcs}
    if sub:
        obj["subresources"] = sub
    return obj


def to_json(resource_cost_breakdowns: List[ResourceCostBreakdown]) -> str:
    return json.dumps([_create_json_obj(b) for b in resource_cost_breakdowns], indent=2)
