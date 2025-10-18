# tests/integration/aws/test_lb_alb_nlb.py
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Dict, Optional

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# -------- duck-typed helpers (work with method/attr variants) --------

def _d(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)

def _call(obj: Any, *names: str, default=None):
    for n in names:
        if hasattr(obj, n):
            a = getattr(obj, n)
            if callable(a):
                try:
                    return a()
                except TypeError:
                    pass
            else:
                return a
    return default

def _pcs(res) -> list[Any]:
    v = _call(res, "price_components", "PriceComponents", default=[])
    return list(v) if isinstance(v, Iterable) else []

def _pc_name(pc) -> str:
    return _call(pc, "name", "Name") or "<component>"

def _pc_unit(pc) -> str:
    return (_call(pc, "unit", "Unit", "unit_", default="") or "").lower()

def _pc_price(pc) -> Decimal:
    return _d(_call(pc, "Price", "price", default=0))

def _pc_hourly(pc) -> Decimal:
    return _d(_call(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_price_hash(pc) -> Optional[str]:
    for attr in ("price_hash", "_price_hash", "PriceHash"):
        v = getattr(pc, attr, None)
        if isinstance(v, str):
            return v
        if callable(v):
            try:
                vv = v()
                if isinstance(vv, str):
                    return vv
            except Exception:
                pass
    meta = getattr(pc, "metadata", None)
    if isinstance(meta, dict):
        h = meta.get("priceHash") or meta.get("price_hash")
        if isinstance(h, str):
            return h
    return None

def _addr(res) -> str:
    return _call(res, "address", "Address", "name", "Name") or "<resource>"

def _runner():
    return GraphQLQueryRunner(os.getenv("PLANCOSTS_PRICE_API", "http://127.0.0.1:4000/graphql"))


# ---------------- plan JSON matching the Go test ----------------

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
                    "address": "aws_lb.lb1",
                    "type": "aws_lb",
                    "values": {"load_balancer_type": "application"},
                },
                {
                    "address": "aws_alb.alb1",
                    "type": "aws_alb",
                    "values": {},  # default to application
                },
                {
                    "address": "aws_lb.nlb1",
                    "type": "aws_lb",
                    "values": {"load_balancer_type": "network"},
                },
            ]
        }
    },
}


@pytest.mark.integration
def test_lb_alb_nlb_price_components_and_hashes():
    resources = parse_plan_json(PLAN)
    get_cost_breakdowns(_runner(), resources)

    # lb1 (application)
    lb1 = next((r for r in resources if _addr(r) == "aws_lb.lb1"), None)
    assert lb1 is not None, "aws_lb.lb1 not parsed/priced"
    comps = { _pc_name(pc): pc for pc in _pcs(lb1) }
    name = "Per Application Load Balancer"
    assert name in comps, f"aws_lb.lb1 components: {sorted(comps.keys())}"
    pc = comps[name]
    assert "hour" in _pc_unit(pc), f"unexpected unit for lb1: {_pc_unit(pc)!r}"
    assert _pc_hourly(pc) == _pc_price(pc), "lb1 hourly should equal unit price (qty=1/hour)"
    assert _pc_price_hash(pc) == "e31cdaab3eb4b520a8e845c058e09e75-d2c98780d7b6e36641b521f1f8145c6f"

    # alb1 (alias of application)
    alb1 = next((r for r in resources if _addr(r) == "aws_alb.alb1"), None)
    assert alb1 is not None, "aws_alb.alb1 not parsed/priced"
    comps = { _pc_name(pc): pc for pc in _pcs(alb1) }
    assert name in comps, f"aws_alb.alb1 components: {sorted(comps.keys())}"
    pc = comps[name]
    assert "hour" in _pc_unit(pc)
    assert _pc_hourly(pc) == _pc_price(pc)
    assert _pc_price_hash(pc) == "e31cdaab3eb4b520a8e845c058e09e75-d2c98780d7b6e36641b521f1f8145c6f"

    # nlb1 (network)
    nlb1 = next((r for r in resources if _addr(r) == "aws_lb.nlb1"), None)
    assert nlb1 is not None, "aws_lb.nlb1 not parsed/priced"
    comps = { _pc_name(pc): pc for pc in _pcs(nlb1) }
    nlb_name = "Per Network Load Balancer"
    assert nlb_name in comps, f"aws_lb.nlb1 components: {sorted(comps.keys())}"
    pc = comps[nlb_name]
    assert "hour" in _pc_unit(pc)
    assert _pc_hourly(pc) == _pc_price(pc)
    assert _pc_price_hash(pc) == "cb019b908c3e3b33bb563bc3040f2e0b-d2c98780d7b6e36641b521f1f8145c6f"
