# plancosts/base/costs.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
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


def _create_price_component_cost(pc: PriceComponent, _query_result: Any) -> PriceComponentCost:
    """Compute hourly + monthly costs for a single price component."""
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(price_component=pc, hourly_cost=hourly, monthly_cost=monthly)


def _extract_price_usd_from_result(query_result: Any) -> Decimal:
    """
    Preferred (new schema):
      data.products[].prices[].USD
    Fallback (legacy aws-prices-graphql):
      data.products[].onDemandPricing[].priceDimensions[].pricePerUnit.USD
    """
    try:
        products = (query_result or {}).get("data", {}).get("products", []) or []
        if not products:
            return Decimal("0")

        p0 = products[0]

        prices = p0.get("prices")
        if isinstance(prices, list) and prices:
            usd = prices[0].get("USD")
            if usd is not None:
                return Decimal(str(usd))

        odp = p0.get("onDemandPricing")
        if isinstance(odp, list) and odp:
            dims = odp[0].get("priceDimensions") or []
            if dims:
                usd = (dims[0].get("pricePerUnit") or {}).get("USD")
                if usd is not None:
                    return Decimal(str(usd))
    except InvalidOperation:
        logging.debug("Price string could not be parsed; treating as 0. (%s)", query_result)
    except Exception:
        pass

    return Decimal("0")


def _set_price_component_price(resource: Resource, pc: PriceComponent, query_result: Any) -> None:
    """
    Extract USD unit price from the GraphQL result and set it on the price component.
    Logs like the Go code (includes resource address and component name).
    """
    res_addr = resource.address()
    pc_name = pc.name()
    try:
        products = (query_result or {}).get("data", {}).get("products", []) or []
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
            price = _extract_price_usd_from_result(query_result)
    except Exception:
        price = Decimal("0")

    pc.set_price(price)


def _get_cost_breakdown(resource: Resource, results: Dict[Resource, Dict[PriceComponent, Any]]) -> ResourceCostBreakdown:
    """
    Build the breakdown for a resource using the previously fetched results map.
    Recurses into sub-resources.
    """
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
    Commit-parity flow:
      1) For each resource, batch GraphQL queries (done by runner), collect results.
      2) For each (resource, priceComponent) result, set the unit price on the PC.
      3) Build recursive cost breakdown trees.
      4) Skip resources with has_cost() == False when producing the final list.
    """
    cost_breakdowns: List[ResourceCostBreakdown] = []

    # Gather results for all resources and set prices
    results_by_resource: Dict[Resource, Dict[PriceComponent, Any]] = {}
    for r in resources:
        resource_results = runner.run_queries(r)
        results_by_resource.update(resource_results)

        # Set unit price on each price component using the query result
        for rr, pc_map in resource_results.items():
            for pc, result in pc_map.items():
                _set_price_component_price(rr, pc, result)

    # Build breakdowns (respect has_cost here)
    for r in resources:
        if not r.has_cost():
            continue
        cost_breakdowns.append(_get_cost_breakdown(r, results_by_resource))

    # Sort for stable output (match Go’s stable presentation)
    cost_breakdowns.sort(key=lambda b: b.resource.address())
    return cost_breakdowns


# Back-compat alias used by some callers
def get_cost_breakdowns(
    runner,
    resources: List[Resource],
) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(runner, resources)
