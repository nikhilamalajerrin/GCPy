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
    # Present so integration tests can assert exact price identity
    price_hash: str = ""


@dataclass
class ResourceCostBreakdown:
    resource: Resource
    price_component_costs: List[PriceComponentCost]
    sub_resource_costs: List["ResourceCostBreakdown"]


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


def _extract_price_hash_from_result(query_result: Any) -> str:
    """
    Pull priceHash if the API returns it:
      data.products[0].prices[0].priceHash
    If not present, return "".
    """
    try:
        products = (query_result or {}).get("data", {}).get("products", []) or []
        if not products:
            return ""
        prices = products[0].get("prices") or []
        if isinstance(prices, list) and prices:
            ph = prices[0].get("priceHash")
            return str(ph) if ph is not None else ""
    except Exception:
        pass
    return ""


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


def _create_price_component_cost(pc: PriceComponent, query_result: Any) -> PriceComponentCost:
    """Compute hourly + monthly costs for a single price component."""
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(
        price_component=pc,
        hourly_cost=hourly,
        monthly_cost=monthly,
        price_hash=_extract_price_hash_from_result(query_result),
    )


def _get_cost_breakdown(
    resource: Resource,
    results: Dict[Resource, Dict[PriceComponent, Any]],
) -> ResourceCostBreakdown:
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
    
    # Sort sub_resource_costs by resource address for stable ordering
    sub_costs.sort(key=lambda b: b.resource.address())

    return ResourceCostBreakdown(
        resource=resource,
        price_component_costs=pc_costs,
        sub_resource_costs=sub_costs,
    )


def generate_cost_breakdowns(
    runner_or_resources,
    resources: List[Resource] | None = None,
) -> List[ResourceCostBreakdown]:
    """
    Back-compat entrypoint:

      New API:
        generate_cost_breakdowns(runner, resources)

      Legacy test style:
        monkeypatch plancosts.base.costs.run_queries, then call
        generate_cost_breakdowns(resources)

    In legacy mode we wrap the monkeypatched module-level `run_queries(resource)`
    in a tiny runner that exposes .run_queries(resource).
    """
    if resources is None:
        # Legacy mode: first arg is actually the resources list
        resources = runner_or_resources

        class _Runner:
            def run_queries(self, resource):
                return run_queries(resource)  # provided by test monkeypatch

        runner = _Runner()
    else:
        # New mode
        runner = runner_or_resources

    cost_breakdowns: List[ResourceCostBreakdown] = []

    # Collect results per resource and set prices on each price component
    results_by_resource: Dict[Resource, Dict[PriceComponent, Any]] = {}
    for r in resources:
        if not r.has_cost():
            continue
            
        resource_results = runner.run_queries(r)
        results_by_resource.update(resource_results)

        for rr, pc_map in resource_results.items():
            for pc, result in pc_map.items():
                _set_price_component_price(rr, pc, result)

    # Build breakdowns for costable resources
    for r in resources:
        if not r.has_cost():
            continue
        cost_breakdowns.append(_get_cost_breakdown(r, results_by_resource))

    cost_breakdowns.sort(key=lambda b: b.resource.address())
    return cost_breakdowns


# Back-compat alias used by some callers
def get_cost_breakdowns(
    runner,
    resources: List[Resource],
) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(runner, resources)


# --- Test shim: legacy monkeypatch target ---
def run_queries(_resource):  # pragma: no cover
    """
    Placeholder only so tests can monkeypatch `plancosts.base.costs.run_queries`.
    Real code paths use `generate_cost_breakdowns(runner, resources)`.
    """
    raise NotImplementedError("This function is intended to be monkeypatched in tests.")