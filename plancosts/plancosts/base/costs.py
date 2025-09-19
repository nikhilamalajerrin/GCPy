# plancosts/base/costs.py
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import logging  
from plancosts.base.resource import Resource, PriceComponent
from plancosts.base.query import GraphQLQueryRunner, extract_price_from_result

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

def _set_price_from_query(pc, result):
    try:
        products = (result or {}).get("data", {}).get("products", []) or []
        addr = getattr(pc, "resource", None)
        # Try to get address for logging
        if callable(addr):
            try:
                res = pc.resource()
                res_addr = getattr(res, "address", None)
                if callable(res_addr):
                    res_addr = res_addr()
                elif res_addr is None:
                    res_addr = getattr(res, "Address", lambda: "")()
            except Exception:
                res_addr = ""
        else:
            res_addr = ""

        if not products:
            if res_addr:
                logging.warning("No prices found for %s, using 0.00", res_addr)
            price = Decimal("0")
        else:
            if len(products) > 1 and res_addr:
                logging.warning("Multiple prices found for %s, using the first price", res_addr)
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

def _pc_cost(pc: PriceComponent) -> PriceComponentCost:
    hourly = pc.hourly_cost()
    monthly = _round6(hourly * HOURS_IN_MONTH)
    return PriceComponentCost(pc, hourly, monthly)

def _breakdown_for(resource: Resource, results_map: Dict[Resource, Dict[PriceComponent, Any]]) -> ResourceCostBreakdown:
    # sort price components by name for stable diffs
    pcs: List[PriceComponentCost] = []
    for pc in sorted(resource.price_components(), key=lambda p: p.name()):
        if pc in results_map.get(resource, {}):
            hourly = pc.hourly_cost()
            monthly = _round6(hourly * HOURS_IN_MONTH)
            pcs.append(PriceComponentCost(pc, hourly, monthly))

    # sort sub-resources by address for stable diffs
    subs: List[ResourceCostBreakdown] = []
    for sub in sorted(resource.sub_resources(), key=lambda r: r.address()):
        if results_map.get(sub):
            subs.append(_breakdown_for(sub, results_map))

    return ResourceCostBreakdown(resource, pcs, subs)

# ---- Compatibility shim expected by tests -------------------------------------
# Tests monkeypatch costs_mod.run_queries, so keep this symbol at module scope.
def run_queries(resource: Resource) -> Dict[Resource, Dict[PriceComponent, Any]]:
    """Default runner-based implementation; test can monkeypatch this."""
    return GraphQLQueryRunner().run_queries(resource)

# ---- Flexible API: supports both (resources) and (runner, resources) ----------

def generate_cost_breakdowns(
    runner_or_resources,  # GraphQLQueryRunner | List[Resource]
    maybe_resources: Optional[List[Resource]] = None,
) -> List[ResourceCostBreakdown]:
    """
    Supports:
      - generate_cost_breakdowns(resources)
      - generate_cost_breakdowns(runner, resources)
    The first form uses the module-level run_queries() so tests can monkeypatch it.
    """
    # Determine call style
    if maybe_resources is None:
        resources: List[Resource] = runner_or_resources  # type: ignore[assignment]
        # Use shim so monkeypatch works
        all_results: Dict[Resource, Dict[PriceComponent, Any]] = {}
        for r in resources:
            rmap = run_queries(r)
            for rr, pcs in rmap.items():
                for pc, result in pcs.items():
                    _set_price_from_query(pc, result)
            all_results.update(rmap)
    else:
        runner: GraphQLQueryRunner = runner_or_resources  # type: ignore[assignment]
        resources = maybe_resources
        all_results = {}
        for r in resources:
            rmap = runner.run_queries(r)
            for rr, pcs in rmap.items():
                for pc, result in pcs.items():
                    _set_price_from_query(pc, result)
            all_results.update(rmap)

    # Build breakdowns
    out: List[ResourceCostBreakdown] = []
    for r in sorted(resources, key=lambda rs: rs.address()):
        if not r.has_cost():
            continue
        out.append(_breakdown_for(r, all_results))
    return out

# Backward-compatible alias used by main.py
def get_cost_breakdowns(
    runner_or_resources,
    maybe_resources: Optional[List[Resource]] = None,
) -> List[ResourceCostBreakdown]:
    return generate_cost_breakdowns(runner_or_resources, maybe_resources)
