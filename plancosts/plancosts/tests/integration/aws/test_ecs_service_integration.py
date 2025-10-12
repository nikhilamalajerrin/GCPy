# plancosts/plancosts/tests/integration/aws/test_ecs_service_integration.py
from __future__ import annotations

import json
from decimal import Decimal
import pytest

#from plancosts.parsers.terraform import parse_plan_json
from plancosts.terraform import load_plan_json, generate_plan_json, parse_plan_json


def _price_components(res):
    pcs = None
    if hasattr(res, "price_components") and callable(getattr(res, "price_components")):
        pcs = res.price_components()
    else:
        pcs = getattr(res, "price_components", None)
    return list(pcs or [])


def _pc_name(pc) -> str:
    n = getattr(pc, "name", None)
    if callable(n):
        return n()
    if isinstance(n, str):
        return n
    return getattr(pc, "_name", "<unknown>")


def _resource_count(res) -> int:
    for attr in ("resource_count", "count"):
        v = getattr(res, attr, None)
        if callable(v):
            try:
                return int(v())
            except Exception:
                pass
        elif v is not None:
            try:
                return int(v)
            except Exception:
                pass
    return 1


def _get_component(res, name: str):
    for pc in _price_components(res):
        if _pc_name(pc) == name:
            return pc
    return None


@pytest.mark.integration
def test_ecs_service_integration():
    """
    Python equivalent of internal/terraform/aws/ecs_service_test.go

    Ensures an ECS Fargate service (desired_count=2) adds:
      - CPU hours
      - GB hours
      - Accelerator hours (eia2.medium)
    And scales costs by desired_count if price APIs are exposed.
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
                            "requires_compatibilities": {
                                "constant_value": ["FARGATE"]
                            },
                            "family": {"constant_value": "ecs_task1"},
                            "memory": {"constant_value": "1 GB"},
                            "cpu": {"constant_value": "1 vCPU"},
                            "inference_accelerator": [
                                {
                                    "device_name": {"constant_value": "device1"},
                                    "device_type": {"constant_value": "eia2.medium"},
                                }
                            ],
                            "container_definitions": {
                                "constant_value": json.dumps(
                                    [
                                        {
                                            "command": ["sleep", "10"],
                                            "entryPoint": ["/"],
                                            "essential": True,
                                            "image": "alpine",
                                            "name": "alpine",
                                            "network_mode": "none",
                                        }
                                    ]
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
                            "task_definition": {
                                "references": ["aws_ecs_task_definition.ecs_task1"]
                            },
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
                            "memory": "1 GB",
                            "cpu": "1 vCPU",
                            "inference_accelerator": [
                                {"device_name": "device1", "device_type": "eia2.medium"}
                            ],
                            "container_definitions": json.dumps(
                                [
                                    {
                                        "command": ["sleep", "10"],
                                        "entryPoint": ["/"],
                                        "essential": True,
                                        "image": "alpine",
                                        "name": "alpine",
                                        "network_mode": "none",
                                    }
                                ]
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

    resources = parse_plan_json(plan)

    svc = next((r for r in resources if r.address() == "aws_ecs_service.ecs_fargate1"), None)
    assert svc is not None, "ECS service not parsed"

    # desired_count scaling
    assert _resource_count(svc) == 2

    # Components present
    expected = {
        "Accelerator hours (eia2.medium)",
        "CPU hours",
        "GB hours",
    }
    names = {_pc_name(pc) for pc in _price_components(svc)}
    for n in expected:
        assert n in names, f"missing price component {n}; got {sorted(names)}"

    # Optional: cost scaling (only if your API exposes price() and hourly_cost())
    def _as_decimal(v):
        try:
            return Decimal(str(v))
        except Exception:
            return None

    for comp_name in expected:
        pc = _get_component(svc, comp_name)
        if pc is None:
            continue

        unit_price = None
        for attr in ("price", "Price"):
            fn = getattr(pc, attr, None)
            if callable(fn):
                unit_price = _as_decimal(fn()); break

        hourly = None
        for attr in ("hourly_cost", "HourlyCost", "hourlyCost"):
            fn = getattr(pc, attr, None)
            if callable(fn):
                hourly = _as_decimal(fn()); break

        if unit_price is not None and hourly is not None:
            assert hourly == unit_price * 2, f"{comp_name}: expected {unit_price}*2, got {hourly}"
