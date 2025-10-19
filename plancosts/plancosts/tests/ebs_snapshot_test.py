# tests/integration/aws/test_ebs_snapshot.py
from __future__ import annotations

from decimal import Decimal
import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


def _pc_name(pc) -> str:
    """Return a price-component's name regardless of impl details."""
    n = getattr(pc, "name", None)
    return n() if callable(n) else (n if isinstance(n, str) else getattr(pc, "_name", "<unknown>"))


def _iter_price_components(res):
    """Iterate price components for a resource, tolerant to attribute/method variants."""
    pcs_attr = getattr(res, "price_components", None)
    if callable(pcs_attr):
        pcs = pcs_attr()
    else:
        pcs = pcs_attr
    for pc in list(pcs or []):
        yield pc


def _monthly_quantity(pc) -> Decimal:
    """Get a component's monthly quantity (Decimal) regardless of naming."""
    # common variants: MonthlyQuantity(), monthly_quantity, quantity(), quantity
    if hasattr(pc, "MonthlyQuantity") and callable(pc.MonthlyQuantity):
        return Decimal(str(pc.MonthlyQuantity()))
    if hasattr(pc, "monthly_quantity"):
        return Decimal(str(getattr(pc, "monthly_quantity")))
    if hasattr(pc, "quantity") and callable(pc.quantity):
        return Decimal(str(pc.quantity()))
    if hasattr(pc, "quantity"):
        return Decimal(str(getattr(pc, "quantity")))
    # default to 0 if not present
    return Decimal(0)


@pytest.mark.integration
def test_ebs_snapshot_storage_from_volume_reference():
    """
    - Define an aws_ebs_volume with size=10 in us-east-1a
    - Define an aws_ebs_snapshot referencing that volume
    - After pricing, snapshot should have a 'Storage' price component with quantity 10 GB-month
    """
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {
                "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
            },
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ebs_volume.gp2",
                        "type": "aws_ebs_volume",
                        "expressions": {
                            "availability_zone": {"constant_value": "us-east-1a"},
                            "size": {"constant_value": 10},
                        },
                    },
                    {
                        "address": "aws_ebs_snapshot.gp2",
                        "type": "aws_ebs_snapshot",
                        "expressions": {
                            # volume_id references the volume, so snapshot size should be derived from it
                            "volume_id": {"references": ["aws_ebs_volume.gp2"]}
                        },
                    },
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ebs_volume.gp2",
                        "type": "aws_ebs_volume",
                        "values": {"availability_zone": "us-east-1a", "size": 10},
                    },
                    {
                        "address": "aws_ebs_snapshot.gp2",
                        "type": "aws_ebs_snapshot",
                        "values": {"volume_id": "aws_ebs_volume.gp2"},
                    },
                ]
            }
        },
    }

    # Parse resources from the synthetic plan
    resources = parse_plan_json(plan)

    # Run pricing (expects your local/mock GraphQL endpoint, same as your snippet)
    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    # Find the snapshot resource
    snap = next((r for r in resources if r.address() == "aws_ebs_snapshot.gp2"), None)
    assert snap is not None, "aws_ebs_snapshot.gp2 resource not found"

    # Ensure there's a "Storage" price component and quantity equals 10 GB-month
    names = {_pc_name(pc) for pc in _iter_price_components(snap)}
    assert "Storage" in names, f"Expected 'Storage' component in {names}"

    storage_pcs = [pc for pc in _iter_price_components(snap) if _pc_name(pc) == "Storage"]
    assert storage_pcs, "No 'Storage' price component found on snapshot"

    qty = _monthly_quantity(storage_pcs[0])
    assert qty == Decimal(10), f"snapshot Storage monthly quantity {qty} != 10"
