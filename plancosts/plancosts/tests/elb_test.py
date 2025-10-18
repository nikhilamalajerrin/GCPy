# tests/integration/aws/test_elb_classic.py
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Dict, Optional

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------- duck-typed helpers (work with attr or method styles) ----------

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

def _price_components(res: Any) -> list[Any]:
    pcs = _call_maybe(res, "price_components", "PriceComponents", default=[])
    return list(pcs) if isinstance(pcs, Iterable) else []

def _pc_name(pc: Any) -> str:
    return _call_maybe(pc, "name", "Name") or "<component>"

def _pc_unit(pc: Any) -> str:
    return _call_maybe(pc, "unit", "Unit", "unit_", default="") or ""

def _pc_price(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "Price", "price", default=0))

def _pc_hourly_cost(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_price_hash(pc: Any) -> Optional[str]:
    # common fields or methods
    for attr in ("price_hash", "_price_hash", "PriceHash"):
        v = getattr(pc, attr, None)
        if isinstance(v, str):
            return v
        if callable(v):
            try:
                val = v()
                if isinstance(val, str):
                    return val
            except Exception:
                pass
    # metadata dict fallback
    meta = getattr(pc, "metadata", None)
    if isinstance(meta, dict):
        h = meta.get("priceHash") or meta.get("price_hash")
        if isinstance(h, str):
            return h
    return None

def _res_address(res: Any) -> str:
    return _call_maybe(res, "address", "Address", "name", "Name") or "<resource>"

def _price_api_url() -> str:
    return os.environ.get("PLANCOSTS_PRICE_API", "http://127.0.0.1:4000/graphql")


# -------------------------- minimal plan JSON --------------------------

PLAN: Dict[str, Any] = {
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
                    "address": "aws_elb.elb1",
                    "type": "aws_elb",
                    "values": {
                        "listener": [
                            {
                                "instance_port": 80,
                                "instance_protocol": "HTTP",
                                "lb_port": 80,
                                "lb_protocol": "HTTP",
                            }
                        ]
                    },
                }
            ]
        }
    },
}


@pytest.mark.integration
def test_elb_classic_hours_component_and_hash():
    # Parse & price
    resources = parse_plan_json(PLAN)
    runner = GraphQLQueryRunner(_price_api_url())
    get_cost_breakdowns(runner, resources)

    elb = next((r for r in resources if _res_address(r) == "aws_elb.elb1"), None)
    assert elb is not None, "aws_elb.elb1 not parsed/priced"

    comps = {_pc_name(pc): pc for pc in _price_components(elb)}

    # Matches Go: component name
    name = "Per Classic Load Balancer"
    assert name in comps, f"Found components: {sorted(comps.keys())}"

    pc = comps[name]

    # Hash parity with Go test
    expected_hash = "52de45f6e7bf85e2d047a2d9674d9eb2-d2c98780d7b6e36641b521f1f8145c6f"
    got_hash = _pc_price_hash(pc)
    assert got_hash == expected_hash, f"expected hash {expected_hash}, got {got_hash}"

    # Quantity math: 1 per hour → hourly cost == unit price
    assert "hour" in _pc_unit(pc).lower(), f"unexpected unit: {_pc_unit(pc)!r}"
    unit_price = _pc_price(pc)
    hourly_cost = _pc_hourly_cost(pc)
    assert hourly_cost == unit_price, f"hourly {hourly_cost} != price {unit_price}"
