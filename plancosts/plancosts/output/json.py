"""
JSON serializer for ResourceCostBreakdown trees.

Structured so `output.table` can render like the Go CLI table.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List

from plancosts.base.costs import PriceComponentCost, ResourceCostBreakdown


def _dec(v: Decimal) -> float:
    # JSON-friendly while preserving sensible precision for display math
    return float(v)


def _pc_cost_to_dict(pcc: PriceComponentCost) -> Dict[str, Any]:
    pc = pcc.price_component
    return {
        "priceComponent": pc.name(),
        "hourlyCost": _dec(pcc.hourly_cost),
        "monthlyCost": _dec(pcc.monthly_cost),
    }


def _rcb_to_dict(rcb: ResourceCostBreakdown) -> Dict[str, Any]:
    return {
        "resource": rcb.resource.address(),
        "breakdown": [_pc_cost_to_dict(p) for p in rcb.price_component_costs],
        "subresources": [_rcb_to_dict(s) for s in rcb.sub_resource_costs],
    }


def to_json(breakdowns: List[ResourceCostBreakdown]) -> str:
    data = [_rcb_to_dict(b) for b in breakdowns]
    return json.dumps(data, separators=(",", ":"), sort_keys=False)
