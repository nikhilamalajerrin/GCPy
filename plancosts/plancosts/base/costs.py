"""
Cost calculation on top of the refactored model.
"""
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
from plancosts.base.resource import Resource, PriceComponent
from plancosts.base.query import run_queries, extract_price_from_result

HOURS_IN_MONTH = Decimal(730)

class PriceComponentCost:
    def __init__(self, price_component: PriceComponent, hourly_cost: Decimal, monthly_cost: Decimal):
        self.price_component = price_component
        self.hourly_cost = hourly_cost
        self.monthly_cost = monthly_cost

class ResourceCostBreakdown:
    def __init__(self, resource: Resource, price_component_costs: List[PriceComponentCost], sub_resource_costs: List["ResourceCostBreakdown"] | None = None):
        self.resource = resource
        self.price_component_costs = price_component_costs
        self.sub_resource_costs = sub_resource_costs or []

def _round6(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

def _set_price(pc: PriceComponent, result: Any) -> None:
    price = Decimal(extract_price_from_result(result))
    pc.set_price(price)

def _pc_cost(pc: PriceComponent, result: Any) -> PriceComponentCost:
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(pc, hourly, monthly)

def _breakdown_for(resource: Resource, results_map: Dict[Resource, Dict[PriceComponent, Any]]) -> ResourceCostBreakdown:
    pc_costs: List[PriceComponentCost] = []
    for pc in resource.price_components():
        result = results_map.get(resource, {}).get(pc)
        if result is not None:
            pc_costs.append(_pc_cost(pc, result))

    sub_costs: List[ResourceCostBreakdown] = []
    for sub in resource.sub_resources():
        sub_results = results_map.get(sub, {})
        if sub_results:
            sub_costs.append(_breakdown_for(sub, results_map))

    return ResourceCostBreakdown(resource, pc_costs, sub_costs)

def generate_cost_breakdowns(resources: List[Resource]) -> List[ResourceCostBreakdown]:
    # 1) Run all queries and set prices on components
    all_results: Dict[Resource, Dict[PriceComponent, Any]] = {}
    for r in resources:
        res = run_queries(r)
        # set prices immediately
        for rr, pcs in res.items():
            for pc, result in pcs.items():
                _set_price(pc, result)
        all_results.update(res)

    # 2) Build breakdowns only for costable resources
    out: List[ResourceCostBreakdown] = []
    for r in resources:
        if not r.has_cost():
            continue
        out.append(_breakdown_for(r, all_results))
    return out

# Backward-compatible alias for your existing main.py
def get_cost_breakdowns(resources: List[Resource]) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(resources)
