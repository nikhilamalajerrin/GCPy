# plancosts/costs/breakdown.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from plancosts.resource.resource import PriceComponent, Resource

HOURS_IN_MONTH = Decimal(730)


def _round6(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


@dataclass
class PriceComponentCost:
    price_component: PriceComponent
    hourly_cost: Decimal
    monthly_cost: Decimal


@dataclass
class ResourceCostBreakdown:
    resource: Resource
    price_component_costs: List[PriceComponentCost]
    sub_resource_costs: List["ResourceCostBreakdown"]


def _create_price_component_cost(pc: PriceComponent, query_result: Any) -> PriceComponentCost:
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(price_component=pc, hourly_cost=hourly, monthly_cost=monthly)


def _set_price_component_price(resource: Resource, pc: PriceComponent, query_result: Any) -> None:
    try:
        products = (query_result or {}).get("data", {}).get("products", []) or []
        res_addr = resource.address()
        pc_name = pc.name()

        if not products:
            logging.warning("No prices found for %s %s, using 0.00", res_addr, pc_name)
            price = Decimal("0")
        else:
            if len(products) > 1:
                logging.warning(
                    "Multiple prices found for %s %s, using the first price",
                    res_addr,
                    pc_name,
                )
            p0 = products[0]
            price_str = (
                p0.get("onDemandPricing", [{}])[0]
                  .get("priceDimensions", [{}])[0]
                  .get("pricePerUnit", {})
                  .get("USD", "0")
            )
            price = Decimal(str(price_str))
    except Exception:
        price = Decimal("0")

    pc.set_price(price)


def _get_cost_breakdown(resource: Resource, results: Dict[Resource, Dict[PriceComponent, Any]]) -> ResourceCostBreakdown:
    pc_costs: List[PriceComponentCost] = []
    for pc in resource.price_components():
        result = results.get(resource, {}).get(pc)
        pc_costs.append(_create_price_component_cost(pc, result))

    sub_costs: List[ResourceCostBreakdown] = []
    for sub in resource.sub_resources():
        sub_costs.append(_get_cost_breakdown(sub, results))

    return ResourceCostBreakdown(
        resource=resource,
        price_component_costs=pc_costs,
        sub_resource_costs=sub_costs,
    )


def generate_cost_breakdowns(
    runner,  # must provide .run_queries(resource) -> Dict[Resource, Dict[PriceComponent, Any]]
    resources: List[Resource],
) -> List[ResourceCostBreakdown]:
    """
    Go-parity pipeline:
      1) Skip non-costable resources before querying.
      2) For each costable resource, batch GraphQL queries and collect results.
      3) Set the unit price on each price component using its query result.
      4) Build recursive cost breakdown trees; sort by resource address.
    """
    cost_breakdowns: List[ResourceCostBreakdown] = []

    # 1) Query only resources that have cost (Go: if !resource.HasCost() continue)
    results_by_resource: Dict[Resource, Dict[PriceComponent, Any]] = {}
    per_resource_results: Dict[Resource, Dict[Resource, Dict[PriceComponent, Any]]] = {}

    for r in resources:
        if not r.has_cost():
            continue
        # Runner returns {resource_or_subresource: {pc: result}}
        res_map = runner.run_queries(r)
        per_resource_results[r] = res_map
        # Also aggregate into a single map so lookups during breakdown are O(1)
        for rr, pc_map in res_map.items():
            results_by_resource.setdefault(rr, {}).update(pc_map)

        # 2) Set unit price for each (pc, result) in this resource's map
        for rr, pc_map in res_map.items():
            for pc, result in pc_map.items():
                _set_price_component_price(rr, pc, result)

    # 3) Build breakdowns (skip non-costable like Go)
    for r in resources:
        if not r.has_cost():
            continue
        cost_breakdowns.append(_get_cost_breakdown(r, results_by_resource))

    # 4) Stable sort by address (Go sorts in output)
    cost_breakdowns.sort(key=lambda b: b.resource.address())
    return cost_breakdowns


# Back-compat alias
def get_cost_breakdowns(runner, resources: List[Resource]) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(runner, resources)
