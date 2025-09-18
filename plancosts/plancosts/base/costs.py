"""
Cost calculation and breakdown logic (resource + subresources).
"""
from __future__ import annotations

from typing import List, Tuple, Dict, Any
from decimal import Decimal, ROUND_HALF_UP

from .resource import Resource
from .pricecomponent import PriceComponent
from .query import build_query, get_query_results, extract_price_from_result

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


def _batch_queries(resource: Resource) -> Tuple[List[Tuple[Resource, PriceComponent]], List[Any]]:
    keys: List[Tuple[Resource, PriceComponent]] = []
    queries: List[Any] = []
    for pc in resource.price_components():
        if pc.should_skip(): continue
        keys.append((resource, pc))
        queries.append(build_query(pc.get_filters()))
    for sub in resource.sub_resources():
        for pc in sub.price_components():
            if pc.should_skip(): continue
            keys.append((sub, pc))
            queries.append(build_query(pc.get_filters()))
    return keys, queries


def _unpack(resource: Resource, keys: List[Tuple[Resource, PriceComponent]], results: List[Any]) -> Tuple[List[Tuple[PriceComponent, Any]], Dict[Resource, List[Tuple[PriceComponent, Any]]]]:
    res_results: List[Tuple[PriceComponent, Any]] = []
    sub_results: Dict[Resource, List[Tuple[PriceComponent, Any]]] = {}
    for i, r in enumerate(results):
        target_res, pc = keys[i]
        pair = (pc, r)
        if target_res is resource:
            res_results.append(pair)
        else:
            sub_results.setdefault(target_res, []).append(pair)
    return res_results, sub_results


def _round6(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _pc_cost(pc: PriceComponent, query_result: Any) -> PriceComponentCost:
    price_str = extract_price_from_result(query_result)
    price = Decimal(price_str) if price_str else Decimal("0")
    hourly = pc.calculate_hourly_cost(price)
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(pc, hourly, monthly)


def get_cost_breakdown(resource: Resource) -> ResourceCostBreakdown:
    keys, queries = _batch_queries(resource)
    results = get_query_results(queries) if queries else []
    res_pairs, sub_pairs_map = _unpack(resource, keys, results)

    res_costs = [_pc_cost(pc, res) for pc, res in res_pairs]

    sub_costs: List[ResourceCostBreakdown] = []
    for sub_res, pairs in sub_pairs_map.items():
        sub_pc_costs = [_pc_cost(pc, res) for pc, res in pairs]
        sub_costs.append(ResourceCostBreakdown(resource=sub_res, price_component_costs=sub_pc_costs))

    return ResourceCostBreakdown(resource=resource, price_component_costs=res_costs, sub_resource_costs=sub_costs)


def get_cost_breakdowns(resources: List[Resource]) -> List[ResourceCostBreakdown]:
    breakdowns: List[ResourceCostBreakdown] = []
    for r in resources:
        if r.non_costable():
            continue
        breakdowns.append(get_cost_breakdown(r))
    return breakdowns
