from __future__ import annotations

from decimal import Decimal
import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


def _pc_name(pc) -> str:
    n = getattr(pc, "name", None)
    return n() if callable(n) else (n if isinstance(n, str) else getattr(pc, "_name", "<unknown>"))


def _iter_price_components(res):
    pcs_attr = getattr(res, "price_components", None)
    pcs = pcs_attr() if callable(pcs_attr) else pcs_attr
    for pc in list(pcs or []):
        yield pc


def _monthly_quantity(pc) -> Decimal:
    # Be resilient to either method or attribute styles
    if hasattr(pc, "MonthlyQuantity") and callable(pc.MonthlyQuantity):
        return Decimal(str(pc.MonthlyQuantity()))
    if hasattr(pc, "monthly_quantity"):
        return Decimal(str(getattr(pc, "monthly_quantity")))
    if hasattr(pc, "monthly_quantity") and callable(pc.monthly_quantity):
        return Decimal(str(pc.monthly_quantity()))
    # Fallback to 0
    return Decimal(0)


@pytest.mark.integration
def test_ebs_snapshot_copy_storage_uses_this_size_when_source_has_volume():
    """
    Mirrors Go test TestEBSSnapshotCopy:

    TF model:
      aws_ebs_volume (size=10) -> aws_ebs_snapshot -> aws_ebs_snapshot_copy

    Expectation:
      The snapshot_copy "Storage" price component should bill for 10 GB-months
      (i.e., use THIS resource's 'size' when the source snapshot chains to a volume).
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
                            "volume_id": {"references": ["aws_ebs_volume.gp2"]}
                        },
                    },
                    {
                        "address": "aws_ebs_snapshot_copy.gp2",
                        "type": "aws_ebs_snapshot_copy",
                        "expressions": {
                            "source_snapshot_id": {
                                "references": ["aws_ebs_snapshot.gp2"]
                            },
                            "source_region": {"constant_value": "us-east-1"},
                            # Explicit size=10 to mirror how Infracost resolves GB from this resource
                            "size": {"constant_value": 10},
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
                        "values": {
                            "availability_zone": "us-east-1a",
                            "size": 10,
                        },
                    },
                    {
                        "address": "aws_ebs_snapshot.gp2",
                        "type": "aws_ebs_snapshot",
                        "values": {"volume_id": "aws_ebs_volume.gp2"},
                    },
                    {
                        "address": "aws_ebs_snapshot_copy.gp2",
                        "type": "aws_ebs_snapshot_copy",
                        "values": {
                            "source_snapshot_id": "aws_ebs_snapshot.gp2",
                            "source_region": "us-east-1",
                            "size": 10,
                        },
                    },
                ]
            }
        },
    }

    resources = parse_plan_json(plan)

    # Uses your local/mock GraphQL price server.
    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    # Locate the snapshot_copy resource
    copy_res = next((r for r in resources if r.address() == "aws_ebs_snapshot_copy.gp2"), None)
    assert copy_res is not None, "aws_ebs_snapshot_copy.gp2 not found"

    # Ensure it has a "Storage" price component
    names = {_pc_name(pc) for pc in _iter_price_components(copy_res)}
    assert "Storage" in names, f"Storage price component missing, found {names}"

    # Quantity should equal THIS resource's 'size' (10 GB-months)
    for pc in _iter_price_components(copy_res):
        if _pc_name(pc) != "Storage":
            continue
        qty = _monthly_quantity(pc)
        assert qty == Decimal(10), f"snapshot_copy GB-month qty {qty} != 10"
