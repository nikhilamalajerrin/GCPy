# tests/integration/aws/test_ebs_volume.py
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
    pcs = getattr(res, "price_components", None)
    pcs = pcs() if callable(pcs) else pcs
    for pc in list(pcs or []):
        yield pc


def _monthly_quantity(pc) -> Decimal:
    if hasattr(pc, "MonthlyQuantity") and callable(pc.MonthlyQuantity):
        return Decimal(str(pc.MonthlyQuantity()))
    if hasattr(pc, "monthly_quantity"):
        return Decimal(str(getattr(pc, "monthly_quantity")))
    if hasattr(pc, "quantity") and callable(pc.quantity):
        return Decimal(str(pc.quantity()))
    if hasattr(pc, "quantity"):
        return Decimal(str(getattr(pc, "quantity")))
    return Decimal(0)


@pytest.mark.integration
def test_ebs_volume_variants():
    # Terraform-like plan JSON with 5 volumes: gp2, standard, io1(+iops), st1, sc1
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
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
                        "address": "aws_ebs_volume.standard",
                        "type": "aws_ebs_volume",
                        "expressions": {
                            "availability_zone": {"constant_value": "us-east-1a"},
                            "size": {"constant_value": 20},
                            "type": {"constant_value": "standard"},
                        },
                    },
                    {
                        "address": "aws_ebs_volume.io1",
                        "type": "aws_ebs_volume",
                        "expressions": {
                            "availability_zone": {"constant_value": "us-east-1a"},
                            "type": {"constant_value": "io1"},
                            "size": {"constant_value": 30},
                            "iops": {"constant_value": 300},
                        },
                    },
                    {
                        "address": "aws_ebs_volume.st1",
                        "type": "aws_ebs_volume",
                        "expressions": {
                            "availability_zone": {"constant_value": "us-east-1a"},
                            "size": {"constant_value": 40},
                            "type": {"constant_value": "st1"},
                        },
                    },
                    {
                        "address": "aws_ebs_volume.sc1",
                        "type": "aws_ebs_volume",
                        "expressions": {
                            "availability_zone": {"constant_value": "us-east-1a"},
                            "size": {"constant_value": 50},
                            "type": {"constant_value": "sc1"},
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
                        "address": "aws_ebs_volume.standard",
                        "type": "aws_ebs_volume",
                        "values": {"availability_zone": "us-east-1a", "size": 20, "type": "standard"},
                    },
                    {
                        "address": "aws_ebs_volume.io1",
                        "type": "aws_ebs_volume",
                        "values": {"availability_zone": "us-east-1a", "type": "io1", "size": 30, "iops": 300},
                    },
                    {
                        "address": "aws_ebs_volume.st1",
                        "type": "aws_ebs_volume",
                        "values": {"availability_zone": "us-east-1a", "size": 40, "type": "st1"},
                    },
                    {
                        "address": "aws_ebs_volume.sc1",
                        "type": "aws_ebs_volume",
                        "values": {"availability_zone": "us-east-1a", "size": 50, "type": "sc1"},
                    },
                ]
            }
        },
    }

    # Build resources and price them via your GraphQL mock/pricing service.
    resources = parse_plan_json(plan)
    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    def assert_storage(res_addr: str, expected_gb: int, expect_iops: int | None = None):
        res = next((r for r in resources if r.address() == res_addr), None)
        assert res is not None, f"resource {res_addr} not found"

        pcs = list(_iter_price_components(res))
        names = {_pc_name(pc) for pc in pcs}

        # Storage component must exist with expected GB
        assert "Storage" in names, f"{res_addr}: missing 'Storage' component"
        storage_pc = next(pc for pc in pcs if _pc_name(pc) == "Storage")
        assert _monthly_quantity(storage_pc) == Decimal(expected_gb), (
            f"{res_addr}: Storage qty {_monthly_quantity(storage_pc)} != {expected_gb}"
        )

        # IOPS only for io1
        if expect_iops is not None:
            assert "Storage IOPS" in names, f"{res_addr}: missing 'Storage IOPS'"
            iops_pc = next(pc for pc in pcs if _pc_name(pc) == "Storage IOPS")
            assert _monthly_quantity(iops_pc) == Decimal(expect_iops), (
                f"{res_addr}: IOPS qty {_monthly_quantity(iops_pc)} != {expect_iops}"
            )
        else:
            assert "Storage IOPS" not in names, f"{res_addr}: unexpected 'Storage IOPS' component"

    assert_storage("aws_ebs_volume.gp2", expected_gb=10)
    assert_storage("aws_ebs_volume.standard", expected_gb=20)
    assert_storage("aws_ebs_volume.io1", expected_gb=30, expect_iops=300)
    assert_storage("aws_ebs_volume.st1", expected_gb=40)
    assert_storage("aws_ebs_volume.sc1", expected_gb=50)
