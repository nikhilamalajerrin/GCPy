from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict


from plancosts.base import costs as costs_mod
from plancosts.tests.mocks import PriceComponentMock as PC
from plancosts.tests.mocks import ResourceMock as R


def _gql_result(usd: Decimal | float | str) -> Dict[str, Any]:
    # Matches the JSON shape expected by extract_price_from_result
    return {
        "data": {
            "products": [
                {
                    "onDemandPricing": [
                        {"priceDimensions": [{"pricePerUnit": {"USD": str(usd)}}]}
                    ]
                }
            ]
        }
    }


def test_generate_cost_breakdowns(monkeypatch):
    # Build the same structure as the Go test:
    # r1 has pc r1pc1 and sub-resource r1.sr1 with pc sr1pc1
    # r2 has pcs r2pc1, r2pc2
    sr1pc1 = PC(Decimal("0.1"), name="sr1pc1")
    r1pc1 = PC(Decimal("0.2"), name="r1pc1")
    r2pc1 = PC(Decimal("0.3"), name="r2pc1")
    r2pc2 = PC(Decimal("0.4"), name="r2pc2")

    r1sr1 = R("r1.sr1", pcs=[sr1pc1])
    r1 = R("r1", pcs=[r1pc1], subs=[r1sr1])
    r2 = R("r2", pcs=[r2pc1, r2pc2])

    # Prepare "overrides" like the Go testQueryRunner:
    # Only r1pc1 gets an override price of 0.01; others get a default 0.1
    override_price = Decimal("0.01")
    default_price = Decimal("0.1")

    def fake_run_queries(resource):
        mapping: dict = {}
        # top-level pcs
        for pc in resource.price_components():
            usd = override_price if (resource is r1 and pc is r1pc1) else default_price
            mapping.setdefault(resource, {})[pc] = _gql_result(usd)
        # sub-resources
        for sub in resource.sub_resources():
            for pc in sub.price_components():
                mapping.setdefault(sub, {})[pc] = _gql_result(default_price)
        return mapping

    # Monkeypatch the function used by generate_cost_breakdowns
    monkeypatch.setattr(costs_mod, "run_queries", fake_run_queries, raising=True)

    result = costs_mod.generate_cost_breakdowns([r1, r2])

    # Check shapes
    assert len(result) == 2

    # r1 expectations
    r1_breakdown = result[0]
    assert r1_breakdown.resource is r1
    # one pc on r1 + one pc on r1.sr1
    assert len(r1_breakdown.price_component_costs) == 1
    assert len(r1_breakdown.sub_resource_costs) == 1
    assert len(r1_breakdown.sub_resource_costs[0].price_component_costs) == 1

    # hourly costs must equal the fixed hourly costs on the components
    # (NOT the fetched price) — this mirrors the Go test.
    H = Decimal("730")
    # r1pc1
    assert r1_breakdown.price_component_costs[0].hourly_cost == Decimal("0.2")
    assert r1_breakdown.price_component_costs[0].monthly_cost == Decimal("0.2") * H
    # r1.sr1 -> sr1pc1
    sr_line = r1_breakdown.sub_resource_costs[0].price_component_costs[0]
    assert sr_line.hourly_cost == Decimal("0.1")
    assert sr_line.monthly_cost == Decimal("0.1") * H

    # r2 expectations
    r2_breakdown = result[1]
    assert r2_breakdown.resource is r2
    assert [c.hourly_cost for c in r2_breakdown.price_component_costs] == [
        Decimal("0.3"),
        Decimal("0.4"),
    ]
    assert [c.monthly_cost for c in r2_breakdown.price_component_costs] == [
        Decimal("0.3") * H,
        Decimal("0.4") * H,
    ]

    # Also validate the fetched price override was stored on r1pc1
    assert r1pc1.price == override_price
