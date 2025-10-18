# tests/integration/aws/test_instance_integration.py
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, List
import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------- small helpers (duck-typed, tolerant to attr/method variants) ----------

def _s(v: Any) -> str:
    return str(v) if v is not None else ""

def _d(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)

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
    return _call_maybe(res, "address", "Address", "name", "Name") or "<resource>"

def _sub_resources(res: Any) -> list[Any]:
    subs = _call_maybe(res, "sub_resources", "SubResources", default=[])
    return list(subs) if isinstance(subs, Iterable) else []

def _price_components(res: Any) -> list[Any]:
    pcs = _call_maybe(res, "price_components", "PriceComponents", default=[])
    return list(pcs) if isinstance(pcs, Iterable) else []

def _pc_name(pc: Any) -> str:
    n = _call_maybe(pc, "name", "Name") or ""
    return str(n)

def _pc_price_hash(pc: Any) -> str | None:
    for attr in ("PriceHash", "price_hash", "get_price_hash"):
        v = getattr(pc, attr, None)
        if callable(v):
            try:
                val = v()
                if isinstance(val, str):
                    return val
            except Exception:
                pass
        elif isinstance(v, str):
            return v
    meta = getattr(pc, "metadata", None)
    if isinstance(meta, dict):
        h = meta.get("priceHash") or meta.get("price_hash")
        if isinstance(h, str):
            return h
    return None

def _pc_price(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "Price", "price", default=0))

def _pc_hourly(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_monthly(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "MonthlyCost", "monthly_cost", default=0))

def _iter_all_resources(resources: list[Any]) -> Iterable[Any]:
    for r in resources:
        yield r
        for s in _sub_resources(r):
            yield s

def _normalize_component_name(resource_name: str, comp_name: str) -> str:
    # Some ports label compute as "Compute (on-demand, m3.medium)" vs "Compute (m3.medium)"
    if resource_name == "aws_instance.instance1" and comp_name.startswith("Compute ("):
        return comp_name.replace("on-demand, ", "")
    return comp_name

def _extract_price_hashes(resources: list[Any]) -> List[list[str]]:
    out: List[list[str]] = []
    for r in _iter_all_resources(resources):
        rname = _res_address(r)
        for pc in _price_components(r):
            h = _pc_price_hash(pc)
            if h:
                cname = _normalize_component_name(rname, _pc_name(pc))
                out.append([rname, cname, h])
    return out

def _find_component(resources: list[Any], resource_name: str, comp_name: str):
    for r in _iter_all_resources(resources):
        if _res_address(r) == resource_name:
            for pc in _price_components(r):
                if _normalize_component_name(resource_name, _pc_name(pc)) == comp_name:
                    return pc
    return None


@pytest.mark.integration
def test_aws_instance_integration():
    # Terraform plan JSON equivalent of the Go test’s HCL
    tf_plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {
                "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
            },
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.instance1",
                        "type": "aws_instance",
                        "expressions": {
                            "instance_type": {"constant_value": "m3.medium"},
                            "tenancy": {"constant_value": "default"},
                            "root_block_device": [
                                {
                                    "volume_type": {"constant_value": "gp2"},
                                    "volume_size": {"constant_value": 10},
                                }
                            ],
                            "ebs_block_device": [
                                {  # [0] gp2 10 GB
                                    "volume_type": {"constant_value": "gp2"},
                                    "volume_size": {"constant_value": 10},
                                },
                                {  # [1] standard 20 GB
                                    "volume_type": {"constant_value": "standard"},
                                    "volume_size": {"constant_value": 20},
                                },
                                {  # [2] sc1 30 GB
                                    "volume_type": {"constant_value": "sc1"},
                                    "volume_size": {"constant_value": 30},
                                },
                                {  # [3] io1 40 GB + 1000 IOPS
                                    "volume_type": {"constant_value": "io1"},
                                    "volume_size": {"constant_value": 40},
                                    "iops": {"constant_value": 1000},
                                },
                            ],
                        },
                    }
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.instance1",
                        "type": "aws_instance",
                        "values": {
                            "instance_type": "m3.medium",
                            "tenancy": "default",
                            "root_block_device": [
                                {"volume_type": "gp2", "volume_size": 10},
                            ],
                            "ebs_block_device": [
                                {"volume_type": "gp2", "volume_size": 10},      # [0]
                                {"volume_type": "standard", "volume_size": 20}, # [1]
                                {"volume_type": "sc1", "volume_size": 30},      # [2]
                                {"volume_type": "io1", "volume_size": 40, "iops": 1000},  # [3]
                            ],
                        },
                    }
                ]
            }
        },
    }

    # 1) Parse plan -> resources
    resources = parse_plan_json(tf_plan)

    # 2) Price + roll up
    runner = GraphQLQueryRunner("http://127.0.0.1:4000/graphql")
    get_cost_breakdowns(runner, resources)

    # 3) Check price hashes (parity with Go test)
    expected_price_hashes = [
        ["aws_instance.instance1", "Compute (m3.medium)", "666e02bbe686f6950fd8a47a55e83a75-d2c98780d7b6e36641b521f1f8145c6f"],
        ["aws_instance.instance1.root_block_device", "Storage", "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[0]", "Storage", "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[1]", "Storage", "0ed17ed1777b7be91f5b5ce79916d8d8-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[2]", "Storage", "3122df29367c2460c76537cccf0eadb5-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[3]", "Storage", "99450513de8c131ee2151e1b319d8143-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[3]", "Storage IOPS", "d5c5e1fb9b8ded55c336f6ae87aa2c3b-9c483347596633f8cf3ab7fdd5502b78"],
    ]

    got_hashes = _extract_price_hashes(resources)
    expected_sorted = sorted(expected_price_hashes, key=lambda x: (x[0], x[1], x[2]))
    got_sorted = sorted(got_hashes, key=lambda x: (x[0], x[1], x[2]))
    assert got_sorted == expected_sorted, f"Got unexpected price hashes\nExpected: {expected_sorted}\nGot:      {got_sorted}"

    # 4) Cost math checks
    # Compute hourly should equal unit price * 1
    comp = _find_component(resources, "aws_instance.instance1", "Compute (m3.medium)")
    assert comp is not None, "missing Compute (m3.medium) (note: we normalize 'on-demand, ' if present)"
    unit = _pc_price(comp)
    hourly = _pc_hourly(comp)
    assert hourly == unit, f"Compute hourly expected {unit}, got {hourly}"

    # Root block device monthly = price * 10 GB
    comp = _find_component(resources, "aws_instance.instance1.root_block_device", "Storage")
    assert comp is not None, "missing root block device Storage"
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(10), f"root_block_device monthly expected {unit}*10, got {monthly}"

    # ebs_block_device[0] 10 GB
    comp = _find_component(resources, "aws_instance.instance1.ebs_block_device[0]", "Storage")
    assert comp is not None
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(10)

    # ebs_block_device[1] 20 GB (standard)
    comp = _find_component(resources, "aws_instance.instance1.ebs_block_device[1]", "Storage")
    assert comp is not None
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(20)

    # ebs_block_device[2] 30 GB (sc1)
    comp = _find_component(resources, "aws_instance.instance1.ebs_block_device[2]", "Storage")
    assert comp is not None
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(30)

    # ebs_block_device[3] Storage 40 GB (io1)
    comp = _find_component(resources, "aws_instance.instance1.ebs_block_device[3]", "Storage")
    assert comp is not None
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(40)

    # ebs_block_device[3] Storage IOPS 1000
    comp = _find_component(resources, "aws_instance.instance1.ebs_block_device[3]", "Storage IOPS")
    assert comp is not None
    unit = _pc_price(comp)
    monthly = _pc_monthly(comp)
    assert monthly == unit * Decimal(1000)
