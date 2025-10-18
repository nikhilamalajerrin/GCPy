# tests/integration/terraform/test_provider_load_resources.py
from __future__ import annotations

from typing import Any, Iterable, List
import pytest

from plancosts.providers.terraform.parser import parse_plan_json


# --- duck-typed helpers (tolerate attr vs method differences) ---

def _call_maybe(obj: Any, *names: str, default=None):
    for n in names:
        if hasattr(obj, n):
            attr = getattr(obj, n)
            if callable(attr):
                try:
                    return attr()
                except TypeError:
                    pass
            else:
                return attr
    return default

def _res_address(res: Any) -> str:
    # prefer Address()/address(), else Name()/name
    return (
        _call_maybe(res, "Address", "address")
        or _call_maybe(res, "Name", "name")
        or "<resource>"
    )

def _addresses(resources: Iterable[Any]) -> List[str]:
    return sorted(_res_address(r) for r in resources)


# ---------------------- tests ----------------------

@pytest.mark.unit
def test_load_resources_root_module():
    """
    Parity with Go:
      TestLoadResources_rootModule
    """
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {
                "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
            },
            "root_module": {},
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_nat_gateway.nat1",
                        "type": "aws_nat_gateway",
                        "values": {
                            "allocation_id": "eip-12345678",
                            "subnet_id": "subnet-12345678",
                        },
                    }
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    addrs = _addresses(resources)

    assert "aws_nat_gateway.nat1" in addrs, f"missing aws_nat_gateway.nat1; got {addrs}"


@pytest.mark.unit
def test_load_resources_nested_module():
    """
    Parity with Go:
      TestLoadResources_nestedModule

    Terraform addresses repeat the literal 'module.' segment for each level:
      module.module1.aws_nat_gateway.nat1
      module.module1.module.module2.aws_nat_gateway.nat2
    """
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {
                "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
            },
            "root_module": {},
        },
        "planned_values": {
            "root_module": {
                "resources": [],
                "child_modules": [
                    {
                        "address": "module.module1",
                        "resources": [
                            {
                                "address": "module.module1.aws_nat_gateway.nat1",
                                "type": "aws_nat_gateway",
                                "values": {
                                    "allocation_id": "eip-12345678",
                                    "subnet_id": "subnet-12345678",
                                },
                            }
                        ],
                        "child_modules": [
                            {
                                "address": "module.module1.module.module2",
                                "resources": [
                                    {
                                        "address": "module.module1.module.module2.aws_nat_gateway.nat2",
                                        "type": "aws_nat_gateway",
                                        "values": {
                                            "allocation_id": "eip-12345678",
                                            "subnet_id": "subnet-12345678",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        },
    }

    resources = parse_plan_json(plan)
    addrs = _addresses(resources)

    assert "module.module1.aws_nat_gateway.nat1" in addrs, (
        f"missing module.module1.aws_nat_gateway.nat1; got {addrs}"
    )
    assert "module.module1.module.module2.aws_nat_gateway.nat2" in addrs, (
        f"missing module.module1.module.module2.aws_nat_gateway.nat2; got {addrs}"
    )
