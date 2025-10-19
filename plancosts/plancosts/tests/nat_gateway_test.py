# tests/integration/aws/test_nat_gateway_integration.py
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Dict, Optional

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# -------------------- duck-typed helpers (robust) --------------------

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

def _price_components(res) -> list[Any]:
    pcs = _call_maybe(res, "price_components", "PriceComponents", default=[])
    return list(pcs) if isinstance(pcs, Iterable) else []

def _pc_name(pc) -> str:
    return _call_maybe(pc, "name", "Name") or "<component>"

def _pc_unit(pc) -> str:
    # Support unit, Unit, unit_ (BaseAwsPriceComponent uses unit_)
    return _call_maybe(pc, "unit", "Unit", "unit_", default="") or ""

def _pc_price(pc) -> Decimal:
    return _d(_call_maybe(pc, "Price", "price", default=0))

def _pc_hourly_cost(pc) -> Decimal:
    return _d(_call_maybe(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_monthly_cost(pc) -> Decimal:
    return _d(_call_maybe(pc, "MonthlyCost", "monthly_cost", default=0))

def _pc_monthly_qty(pc) -> Decimal:
    q = _call_maybe(pc, "MonthlyQuantity", "monthly_quantity", "Quantity", "quantity", default=0)
    return _d(q)

def _pc_price_hash(pc) -> Optional[str]:
    for attr in ("PriceHash", "price_hash", "_price_hash", "get_price_hash"):
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
    meta = getattr(pc, "metadata", None)
    if isinstance(meta, dict):
        h = meta.get("priceHash") or meta.get("price_hash")
        if isinstance(h, str):
            return h
    return None

def _res_address(res) -> str:
    return _call_maybe(res, "address", "Address", "name", "Name") or "<resource>"

def _price_api_url() -> str:
    # Default matches the mock used in CI; override via env if needed
    return os.environ.get("PLANCOSTS_PRICE_API", "http://127.0.0.1:4000/graphql")


# -------------------- minimal plan (no explicit usage) --------------------

PLAN_BASE: Dict[str, Any] = {
    "format_version": "0.1",
    "terraform_version": "0.14.0",
    "configuration": {
        "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
        "root_module": {},
    },
    "planned_values": {
        "root_module": {
            "resources": [
                {
                    "address": "aws_nat_gateway.nat",
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


@pytest.mark.integration
def test_nat_gateway_components_and_hashes():
    """
    TestNATGateway:
      - Two components with exact names
      - Exact price hashes
      - Hourly charge for the gateway (qty=1 per hour)
      - Per-GB component defaults to zero quantity when no usage provided
    """
    resources = parse_plan_json(PLAN_BASE)
    runner = GraphQLQueryRunner(_price_api_url())
    get_cost_breakdowns(runner, resources)

    nat = next((r for r in resources if _res_address(r) == "aws_nat_gateway.nat"), None)
    assert nat is not None, "aws_nat_gateway.nat not parsed/priced"

    comps = { _pc_name(pc): pc for pc in _price_components(nat) }

    # Expected names
    per_nat_name = "Per NAT Gateway"
    per_gb_name = "Per GB data processed"
    assert per_nat_name in comps, f"Found components: {sorted(comps.keys())}"
    assert per_gb_name in comps, f"Found components: {sorted(comps.keys())}"

    # Expected hashes
    assert _pc_price_hash(comps[per_nat_name]) == "6e137a9da0718f0ec80fb60866730ba9-d2c98780d7b6e36641b521f1f8145c6f"
    assert _pc_price_hash(comps[per_gb_name]) == "96ea6ef0b38f7b8b243f50e02dfa8fa8-b1ae3861dc57e2db217fa83a7420374f"

    # Per NAT Gateway: hourly cost equals unit price (qty=1 per hour)
    per_nat = comps[per_nat_name]
    unit = _pc_unit(per_nat)
    assert "hour" in unit.lower(), f"Unexpected unit for {per_nat_name}: {unit!r}"
    assert _pc_hourly_cost(per_nat) == _pc_price(per_nat), "Per NAT Gateway hourly should equal unit price"

    # Per GB data processed: no usage -> zero quantity & zero monthly cost
    per_gb = comps[per_gb_name]
    assert _pc_unit(per_gb).upper() == "GB", f"Unexpected unit for {per_gb_name}: {_pc_unit(per_gb)!r}"
    assert _pc_monthly_qty(per_gb) == 0, f"Expected 0 quantity, got {_pc_monthly_qty(per_gb)}"
    assert _pc_monthly_cost(per_gb) == 0, f"Expected 0 monthly cost, got {_pc_monthly_cost(per_gb)}"


@pytest.mark.integration
def test_nat_gateway_usage_monthly_gb():
    """
    When monthly GB usage is provided, monthly cost = unit price * usage_gb.
    """
    resources = parse_plan_json(PLAN_BASE)

    # Attach usage to the resource (port-friendly)
    nat = next((r for r in resources if _res_address(r) == "aws_nat_gateway.nat"), None)
    assert nat is not None, "aws_nat_gateway.nat not parsed"
    usage_payload = {"monthly_gb_data_processed": 100} 
    if hasattr(nat, "set_usage") and callable(getattr(nat, "set_usage")):
        nat.set_usage(usage_payload)  # type: ignore[attr-defined]
    else:
        setattr(nat, "_usage", usage_payload)

    runner = GraphQLQueryRunner(_price_api_url())
    get_cost_breakdowns(runner, resources)

    comps = { _pc_name(pc): pc for pc in _price_components(nat) }

    # Price hash for per-GB stays the same as no-usage case
    per_gb_name = "Per GB data processed"
    per_gb = comps.get(per_gb_name)
    assert per_gb is not None, f"{per_gb_name} component not found"
    assert _pc_price_hash(per_gb) == "96ea6ef0b38f7b8b243f50e02dfa8fa8-b1ae3861dc57e2db217fa83a7420374f"

    qty = _pc_monthly_qty(per_gb)
    assert qty == Decimal(100), f"Expected monthly quantity 100, got {qty}"

    unit_price = _pc_price(per_gb)
    monthly_cost = _pc_monthly_cost(per_gb)
    expected = unit_price * Decimal(100)
    assert monthly_cost == expected, f"Expected {unit_price} * 100 = {expected}, got {monthly_cost}"
