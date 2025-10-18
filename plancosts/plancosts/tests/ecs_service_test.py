# tests/integration/aws/test_ecs_service.py
from __future__ import annotations

import json
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


@pytest.mark.integration
def test_ecs_service():
    # Terraform-like plan JSON matching the Go test's intent:
    # - ECS cluster with FARGATE capacity provider
    # - Task def: 2 GB memory, 1 vCPU, one eia2.medium accelerator
    # - Service: desired_count = 2
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ecs_cluster.ecs1",
                        "type": "aws_ecs_cluster",
                        "expressions": {
                            "name": {"constant_value": "ecs1"},
                            "capacity_providers": {"constant_value": ["FARGATE"]},
                        },
                    },
                    {
                        "address": "aws_ecs_task_definition.ecs_task1",
                        "type": "aws_ecs_task_definition",
                        "expressions": {
                            "requires_compatibilities": {"constant_value": ["FARGATE"]},
                            "family": {"constant_value": "ecs_task1"},
                            "memory": {"constant_value": "2 GB"},
                            "cpu": {"constant_value": "1 vCPU"},
                            "inference_accelerator": [
                                {
                                    "device_name": {"constant_value": "device1"},
                                    "device_type": {"constant_value": "eia2.medium"},
                                }
                            ],
                            "container_definitions": {
                                "constant_value": json.dumps(
                                    [{
                                        "command": ["sleep", "10"],
                                        "entryPoint": ["/"],
                                        "essential": True,
                                        "image": "alpine",
                                        "name": "alpine",
                                        "network_mode": "none",
                                    }]
                                )
                            },
                        },
                    },
                    {
                        "address": "aws_ecs_service.ecs_fargate1",
                        "type": "aws_ecs_service",
                        "expressions": {
                            "name": {"constant_value": "ecs_fargate1"},
                            "launch_type": {"constant_value": "FARGATE"},
                            "cluster": {"references": ["aws_ecs_cluster.ecs1"]},
                            "task_definition": {"references": ["aws_ecs_task_definition.ecs_task1"]},
                            "desired_count": {"constant_value": 2},
                        },
                    },
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_ecs_cluster.ecs1",
                        "type": "aws_ecs_cluster",
                        "values": {
                            "name": "ecs1",
                            "capacity_providers": ["FARGATE"],
                            "default_capacity_provider_strategy": [],
                            "tags": None,
                        },
                    },
                    {
                        "address": "aws_ecs_task_definition.ecs_task1",
                        "type": "aws_ecs_task_definition",
                        "values": {
                            "requires_compatibilities": ["FARGATE"],
                            "family": "ecs_task1",
                            "memory": "2 GB",
                            "cpu": "1 vCPU",
                            "inference_accelerator": [
                                {"device_name": "device1", "device_type": "eia2.medium"}
                            ],
                            "container_definitions": json.dumps(
                                [{
                                    "command": ["sleep", "10"],
                                    "entryPoint": ["/"],
                                    "essential": True,
                                    "image": "alpine",
                                    "name": "alpine",
                                    "network_mode": "none",
                                }]
                            ),
                            "tags": None,
                            "volume": [],
                        },
                    },
                    {
                        "address": "aws_ecs_service.ecs_fargate1",
                        "type": "aws_ecs_service",
                        "values": {
                            "name": "ecs_fargate1",
                            "launch_type": "FARGATE",
                            "desired_count": 2,
                            "deployment_maximum_percent": 200,
                            "deployment_minimum_healthy_percent": 100,
                            "enable_ecs_managed_tags": False,
                            "scheduling_strategy": "REPLICA",
                            "capacity_provider_strategy": [],
                            "deployment_controller": [],
                            "load_balancer": [],
                            "network_configuration": [],
                            "ordered_placement_strategy": [],
                            "placement_constraints": [],
                            "propagate_tags": None,
                            "service_registries": [],
                            "tags": None,
                        },
                    },
                ]
            }
        },
    }

    # Parse resources from the plan and price them
    resources = parse_plan_json(plan)
    svc = next((r for r in resources if r.address() == "aws_ecs_service.ecs_fargate1"), None)
    assert svc is not None, "ECS service not parsed"

    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    # Expected components from the Go test
    expected_names = {
        "Per GB per hour",
        "Per vCPU per hour",
        "Inference accelerator (eia2.medium)",
    }
    names = {_pc_name(pc) for pc in _iter_price_components(svc)}
    missing = expected_names - names
    assert not missing, f"missing price components: {sorted(missing)}; got {sorted(names)}"

    # Factors per Go test:
    # - memory: 2 GB * desired_count(2) = 4
    # - vCPU: 1 * desired_count(2) = 2
    # - accelerator: 1 * desired_count(2) = 2
    factors = {
        "Per GB per hour": Decimal(4),
        "Per vCPU per hour": Decimal(2),
        "Inference accelerator (eia2.medium)": Decimal(2),
    }

    for pc in _iter_price_components(svc):
        n = _pc_name(pc)
        if n not in factors:
            continue

        # unit price
        if hasattr(pc, "Price") and callable(pc.Price):
            price = Decimal(str(pc.Price()))
        else:
            price = Decimal(str(getattr(pc, "price", "0")))

        # hourly cost
        if hasattr(pc, "HourlyCost") and callable(pc.HourlyCost):
            hourly = Decimal(str(pc.HourlyCost()))
        else:
            hourly = Decimal(str(getattr(pc, "hourly_cost", "0")))

        expected_hourly = price * factors[n]
        assert hourly == expected_hourly, f"{n}: expected {price} * {factors[n]} = {expected_hourly}, got {hourly}"
