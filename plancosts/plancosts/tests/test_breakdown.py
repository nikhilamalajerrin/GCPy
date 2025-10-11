# plancosts/tests/test_breakdown.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any

from plancosts.costs.breakdown import generate_cost_breakdowns, HOURS_IN_MONTH
from plancosts.resource.resource import BaseResource, BasePriceComponent, flatten_sub_resources


class TestQueryRunner:
    """
    Mimics the Go test's QueryRunner by returning per-(resource, price_component)
    price overrides, wrapped in the JSON shape that the code expects:
      {"data":{"products":[{"prices":[{"USD": "<price>"}]}]}}
    """
    def __init__(self, price_overrides: Dict[BaseResource, Dict[BasePriceComponent, Decimal]]):
        self.price_overrides = price_overrides

    def run_queries(self, resource: BaseResource):
        # Build results for the root resource and all of its sub-resources
        all_resources = [resource] + flatten_sub_resources(resource)
        results: Dict[Any, Dict[Any, Any]] = {}
        for r in all_resources:
            pc_map: Dict[Any, Any] = {}
            for pc in r.PriceComponents():
                price = self.price_overrides.get(r, {}).get(pc, Decimal("0"))
                pc_map[pc] = {
                    "data": {
                        "products": [
                            {
                                "prices": [
                                    {"USD": str(price)}
                                ]
                            }
                        ]
                    }
                }
            results[r] = pc_map
        return results


def test_generate_cost_breakdowns():
    # Resources
    r1 = BaseResource("r1", {}, True)
    r1sr1 = BaseResource("r1sr1", {}, True)
    r1.AddSubResource(r1sr1)

    r2 = BaseResource("r2", {}, True)

    # Price components
    r1pc1 = BasePriceComponent("r1pc1", r1, "r1pc1 unit", "hour")
    r1.AddPriceComponent(r1pc1)

    sr1pc1 = BasePriceComponent("sr1pc1", r1sr1, "sr1pc1 unit", "hour")
    r1sr1.AddPriceComponent(sr1pc1)

    r2pc1 = BasePriceComponent("r2pc1", r2, "r2pc1 unit", "hour")
    r2.AddPriceComponent(r2pc1)

    r2pc2 = BasePriceComponent("r2pc2", r2, "r2pc2 unit", "hour")
    r2.AddPriceComponent(r2pc2)

    # Price overrides (like the Go test)
    price_overrides: Dict[BaseResource, Dict[BasePriceComponent, Decimal]] = {
        r1: {r1pc1: Decimal("0.1")},
        r1sr1: {sr1pc1: Decimal("0.2")},
        r2: {r2pc1: Decimal("0.3"), r2pc2: Decimal("0.4")},
    }

    runner = TestQueryRunner(price_overrides)

    # Execute
    result = generate_cost_breakdowns(runner, [r1, r2])

    # Expectation: two top-level breakdowns, ordered by address (r1, r2)
    assert [b.resource.Address() for b in result] == ["r1", "r2"]

    # r1
    r1b = result[0]
    assert [pc.price_component.Name() for pc in r1b.price_component_costs] == ["r1pc1"]
    assert r1b.price_component_costs[0].hourly_cost == Decimal("0.1")
    assert r1b.price_component_costs[0].monthly_cost == Decimal("0.1") * HOURS_IN_MONTH

    # r1 subresource r1sr1
    assert len(r1b.sub_resource_costs) == 1
    r1sr1b = r1b.sub_resource_costs[0]
    assert r1sr1b.resource.Address() == "r1sr1"
    assert [pc.price_component.Name() for pc in r1sr1b.price_component_costs] == ["sr1pc1"]
    assert r1sr1b.price_component_costs[0].hourly_cost == Decimal("0.2")
    assert r1sr1b.price_component_costs[0].monthly_cost == Decimal("0.2") * HOURS_IN_MONTH
    assert r1sr1b.sub_resource_costs == []

    # r2
    r2b = result[1]
    assert [pc.price_component.Name() for pc in r2b.price_component_costs] == ["r2pc1", "r2pc2"]
    assert r2b.price_component_costs[0].hourly_cost == Decimal("0.3")
    assert r2b.price_component_costs[0].monthly_cost == Decimal("0.3") * HOURS_IN_MONTH
    assert r2b.price_component_costs[1].hourly_cost == Decimal("0.4")
    assert r2b.price_component_costs[1].monthly_cost == Decimal("0.4") * HOURS_IN_MONTH
    assert r2b.sub_resource_costs == []
