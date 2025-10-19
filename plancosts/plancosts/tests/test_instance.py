from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, List
import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------- small helpers (duck-typed, tolerant to attr/method variants) ----------

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
    if resource_name.startswith("aws_instance.") and comp_name.startswith("Compute ("):
        return comp_name.replace("on-demand, ", "")
    return comp_name

def _find_component(resources: list[Any], resource_name: str, comp_name: str):
    for r in _iter_all_resources(resources):
        if _res_address(r) == resource_name:
            for pc in _price_components(r):
                if _normalize_component_name(resource_name, _pc_name(pc)) == comp_name:
                    return pc
    return None


def _runner():
    return GraphQLQueryRunner("http://127.0.0.1:4000/graphql")


# ---------- tests ----------

def test_instance_basic():
    """
    aws_instance with t3.small, root volume 10GB, one extra ebs 10GB.
    Validates compute component name/hash and storage component hash/quantities.
    """
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.web",
                        "type": "aws_instance",
                        "expressions": {
                            "instance_type": {"constant_value": "t3.small"},
                            "root_block_device": [{"volume_size": {"constant_value": 10}}],
                            "ebs_block_device": [
                                {
                                    "device_name": {"constant_value": "xvdf"},
                                    "volume_size": {"constant_value": 10},
                                }
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
                        "address": "aws_instance.web",
                        "type": "aws_instance",
                        "values": {
                            "instance_type": "t3.small",
                            "root_block_device": [{"volume_size": 10}],
                            "ebs_block_device": [{"device_name": "xvdf", "volume_size": 10}],
                        },
                    }
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), resources)

    # Compute component (on-demand)
    comp = _find_component(resources, "aws_instance.web", "Compute (t3.small)")
    assert comp is not None, "missing Compute (t3.small) (note: we normalize 'on-demand, ' if present)"
    assert _pc_price_hash(comp) == "ed297854a1dd56ba7b6e2b958de7ac53-d2c98780d7b6e36641b521f1f8145c6f"
    assert _pc_hourly(comp) == _pc_price(comp)  # qty = 1/hour

    # Root block device monthly = price * 10 GB
    comp = _find_component(resources, "aws_instance.web.root_block_device", "Storage")
    assert comp is not None, "missing root_block_device Storage"
    assert _pc_price_hash(comp) == "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly(comp) == _pc_price(comp) * Decimal(10)

    # ebs_block_device[0] 10 GB
    comp = _find_component(resources, "aws_instance.web.ebs_block_device[0]", "Storage")
    assert comp is not None, "missing ebs_block_device[0] Storage"
    assert _pc_price_hash(comp) == "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly(comp) == _pc_price(comp) * Decimal(10)


def test_instance_io1_iops():
    """
    io1 volume should add 'Storage IOPS' priced by IOPS-months.
    """
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.db",
                        "type": "aws_instance",
                        "expressions": {
                            "instance_type": {"constant_value": "t3.medium"},
                            "root_block_device": [{
                                "volume_size": {"constant_value": 20},
                                "volume_type": {"constant_value": "io1"},
                                "iops": {"constant_value": 200},
                            }],
                        },
                    }
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_instance.db",
                        "type": "aws_instance",
                        "values": {
                            "instance_type": "t3.medium",
                            "root_block_device": [{"volume_size": 20, "volume_type": "io1", "iops": 200}],
                        },
                    }
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), resources)

    # Compute
    comp = _find_component(resources, "aws_instance.db", "Compute (t3.medium)")
    assert comp is not None, "missing Compute (t3.medium)"
    assert _pc_price_hash(comp) == "c8faba8210cd512ccab6b71ca400f4de-d2c98780d7b6e36641b521f1f8145c6f"
    assert _pc_hourly(comp) == _pc_price(comp)

    # Root device: io1 storage 20 GB
    comp = _find_component(resources, "aws_instance.db.root_block_device", "Storage")
    assert comp is not None, "missing root_block_device Storage"
    assert _pc_price_hash(comp) == "99450513de8c131ee2151e1b319d8143-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly(comp) == _pc_price(comp) * Decimal(20)

    # Root device: io1 IOPS 200
    comp = _find_component(resources, "aws_instance.db.root_block_device", "Storage IOPS")
    assert comp is not None, "missing root_block_device Storage IOPS"
    assert _pc_price_hash(comp) == "d5c5e1fb9b8ded55c336f6ae87aa2c3b-9c483347596633f8cf3ab7fdd5502b78"
    assert _pc_monthly(comp) == _pc_price(comp) * Decimal(200)
