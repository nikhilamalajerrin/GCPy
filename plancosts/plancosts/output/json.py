# # plancosts/output/json.py
# from __future__ import annotations

# import json
# from decimal import Decimal, ROUND_HALF_UP
# from typing import Any, Dict, List

# from plancosts.base.costs import ResourceCostBreakdown, PriceComponentCost


# def _round6(d: Decimal) -> Decimal:
#     return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# def _pc_cost_to_dict(pcc: PriceComponentCost) -> Dict[str, Any]:
#     pc = pcc.price_component
#     return {
#         "priceComponent": pc.name(),
#         "quantity": str(_round6(Decimal(str(pc.quantity())))),
#         "unit": pc.unit(),
#         "hourlyCost": str(_round6(Decimal(str(pcc.hourly_cost)))),
#         "monthlyCost": str(_round6(Decimal(str(pcc.monthly_cost)))),
#     }


# def _breakdown_to_dict(b: ResourceCostBreakdown) -> Dict[str, Any]:
#     return {
#         "resource": b.resource.address(),
#         "breakdown": [_pc_cost_to_dict(pc) for pc in b.price_component_costs],
#         "subresources": [_breakdown_to_dict(s) for s in b.sub_resource_costs] or [],
#     }


# def to_json(resource_cost_breakdowns: List[ResourceCostBreakdown]) -> str:
#     """
#     Returns a JSON string matching the Go output:
#     [
#       {
#         "resource": "<address>",
#         "breakdown": [
#           {
#             "priceComponent": "...",
#             "quantity": "1.000000",
#             "unit": "hour",
#             "hourlyCost": "0.010400",
#             "monthlyCost": "7.592000"
#           }
#         ],
#         "subresources": [ ... ]
#       }
#     ]
#     """
#     payload = [_breakdown_to_dict(b) for b in resource_cost_breakdowns]
#     return json.dumps(payload)


# plancosts/output/json.py
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from plancosts.base.costs import ResourceCostBreakdown, PriceComponentCost


def _round6(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _safe_decimal(value: Any, field_name: str = "value") -> Decimal:
    """Safely convert any value to Decimal with error handling."""
    try:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except Exception as e:
        print(f"ERROR: Failed to convert {field_name} to Decimal: {repr(value)} (type: {type(value)})")
        print(f"ERROR: Exception: {e}")
        import traceback
        traceback.print_exc()
        return Decimal("0")


def _pc_cost_to_dict(pcc: PriceComponentCost) -> Dict[str, Any]:
    pc = pcc.price_component
    
    try:
        quantity = _safe_decimal(pc.quantity(), "quantity")
        hourly = _safe_decimal(pcc.hourly_cost, "hourlyCost")
        monthly = _safe_decimal(pcc.monthly_cost, "monthlyCost")
        
        return {
            "priceComponent": pc.name(),
            "quantity": str(_round6(quantity)),
            "unit": pc.unit(),
            "hourlyCost": str(_round6(hourly)),
            "monthlyCost": str(_round6(monthly)),
        }
    except Exception as e:
        print(f"ERROR in _pc_cost_to_dict for component: {pc.name()}")
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


def _breakdown_to_dict(b: ResourceCostBreakdown) -> Dict[str, Any]:
    return {
        "resource": b.resource.address(),
        "breakdown": [_pc_cost_to_dict(pc) for pc in b.price_component_costs],
        "subresources": [_breakdown_to_dict(s) for s in b.sub_resource_costs] or [],
    }


def to_json(resource_cost_breakdowns: List[ResourceCostBreakdown]) -> str:
    """
    Returns a JSON string matching the Go output:
    [
      {
        "resource": "<address>",
        "breakdown": [
          {
            "priceComponent": "...",
            "quantity": "1.000000",
            "unit": "hour",
            "hourlyCost": "0.010400",
            "monthlyCost": "7.592000"
          }
        ],
        "subresources": [ ... ]
      }
    ]
    """
    payload = [_breakdown_to_dict(b) for b in resource_cost_breakdowns]
    return json.dumps(payload)