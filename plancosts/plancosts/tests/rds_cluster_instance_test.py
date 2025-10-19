from __future__ import annotations

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


@pytest.mark.integration
def test_rds_cluster_instance_integration():
    rn = "aws_rds_cluster_instance.cluster_instance"
    comp_name = "Database instance"
    expected_hash = "dbf119ea9e222f1fa7ba244500eb005b-d2c98780d7b6e36641b521f1f8145c6f"

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
                        "address": "aws_rds_cluster.default",
                        "type": "aws_rds_cluster",
                        "expressions": {
                            "cluster_identifier": {"constant_value": "aurora-cluster-demo"},
                            "availability_zones": {
                                "constant_value": ["us-east-1a", "us-east-1b", "us-east-1c"]
                            },
                            "database_name": {"constant_value": "mydb"},
                            "master_username": {"constant_value": "foo"},
                            "master_password": {"constant_value": "barbut8chars"},
                        },
                    },
                    {
                        "address": "aws_rds_cluster_instance.cluster_instance",
                        "type": "aws_rds_cluster_instance",
                        "expressions": {
                            "identifier": {"constant_value": "aurora-cluster-demo"},
                            "cluster_identifier": {"references": ["aws_rds_cluster.default"]},
                            "instance_class": {"constant_value": "db.r4.large"},
                            "engine": {"references": ["aws_rds_cluster.default.engine"]},
                            "engine_version": {
                                "references": ["aws_rds_cluster.default.engine_version"]
                            },
                        },
                    },
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_rds_cluster.default",
                        "type": "aws_rds_cluster",
                        "values": {
                            "cluster_identifier": "aurora-cluster-demo",
                            "availability_zones": ["us-east-1a", "us-east-1b", "us-east-1c"],
                            "database_name": "mydb",
                            "master_username": "foo",
                            "master_password": "barbut8chars",
                        },
                    },
                    {
                        "address": "aws_rds_cluster_instance.cluster_instance",
                        "type": "aws_rds_cluster_instance",
                        "values": {
                            "identifier": "aurora-cluster-demo",
                            "cluster_identifier": "aws_rds_cluster.default",
                            "instance_class": "db.r4.large",
                        },
                    },
                ]
            }
        },
    }

    # Parse & price
    resources = parse_plan_json(plan)
    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    inst = next(r for r in resources if r.address() == rn)

    # Collect components by name
    pcs = {}
    pcs_iter = inst.price_components() if callable(getattr(inst, "price_components", None)) else getattr(inst, "price_components", [])  # noqa: E501
    for pc in list(pcs_iter or []):
        name = pc.name() if callable(getattr(pc, "name", None)) else getattr(pc, "name", "")
        pcs[name] = pc

    assert comp_name in pcs, f"components found: {sorted(pcs)}"

    # Price hash
    if hasattr(pcs[comp_name], "PriceHash"):
        got_hash = pcs[comp_name].PriceHash()
    else:
        got_hash = getattr(pcs[comp_name], "price_hash", None)
    assert got_hash == expected_hash, f"expected {expected_hash}, got {got_hash}"

    # Hourly == unit price (qty = 1 per hour)
    price = pcs[comp_name].Price() if hasattr(pcs[comp_name], "Price") else getattr(pcs[comp_name], "price", 0)
    hourly = pcs[comp_name].HourlyCost() if hasattr(pcs[comp_name], "HourlyCost") else getattr(pcs[comp_name], "hourly_cost", 0)  # noqa: E501
    assert hourly == price, f"expected hourly {price}, got {hourly}"
