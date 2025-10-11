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
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(price_component=pc, hourly_cost=hourly, monthly_cost=monthly)


def _extract_price_usd_from_result(query_result: Any) -> Decimal:
    """
    Preferred:
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


def _get_cost_breakdown(
    resource: Resource,
    results: Dict[Resource, Dict[PriceComponent, Any]],
) -> ResourceCostBreakdown:
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
    Pipeline equivalent to pkg/costs/breakdown.go:
      1) Skip non-costable resources before querying.
      2) For each costable resource, batch GraphQL queries and collect results.
      3) Set the unit price on each price component using its query result.
      4) Build recursive breakdown trees; sort by resource address.
    """
    cost_breakdowns: List[ResourceCostBreakdown] = []
    results_by_resource: Dict[Resource, Dict[PriceComponent, Any]] = {}

    for r in resources:
        if not r.has_cost():
            continue

        res_map = runner.run_queries(r)  # {resource_or_subresource: {pc: result}}

        # set prices from this batch
        for rr, pc_map in res_map.items():
            results_by_resource.setdefault(rr, {}).update(pc_map)
            for pc, result in pc_map.items():
                _set_price_component_price(rr, pc, result)

    # Build breakdowns
    for r in resources:
        if not r.has_cost():
            continue
        cost_breakdowns.append(_get_cost_breakdown(r, results_by_resource))

    # Stable order by address
    cost_breakdowns.sort(key=lambda b: b.resource.address())
    return cost_breakdowns


# Back-compat alias
def get_cost_breakdowns(runner, resources: List[Resource]) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(runner, resources)
