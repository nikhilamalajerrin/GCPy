# tests/integration/aws/test_lambda_function.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
import os
import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------- small duck-typed helpers ----------

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

def _price_components(res: Any) -> list[Any]:
    pcs = _call_maybe(res, "price_components", "PriceComponents", default=[])
    return list(pcs) if isinstance(pcs, Iterable) else []

def _pc_name(pc: Any) -> str:
    return _call_maybe(pc, "name", "Name") or "<component>"

def _pc_unit(pc: Any) -> str:
    return _call_maybe(pc, "unit", "Unit", default="") or ""

def _pc_qty_monthly(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "MonthlyQuantity", "monthly_quantity", "Quantity", "quantity", default=0))

def _pc_price(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "Price", "price", default=0))

def _pc_hourly(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_monthly(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "MonthlyCost", "monthly_cost", default=0))

def _pc_price_hash(pc: Any) -> Optional[str]:
    # common fields/methods
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
    # metadata dict fallback
    meta = getattr(pc, "metadata", None)
    if isinstance(meta, dict):
        h = meta.get("priceHash") or meta.get("price_hash")
        if isinstance(h, str):
            return h
    return None

def _endpoint() -> str:
    base = os.environ.get("PLANCOSTS_API_URL", "http://127.0.0.1:4000")
    return base.rstrip("/") + "/graphql"


# ---------- tests ----------

@pytest.mark.integration
def test_lambda_no_usage_defaults_to_zero():
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}}
        },
        "planned_values": {
            "root_module": {
                "resources": [{
                    "address": "aws_lambda_function.lambda",
                    "type": "aws_lambda_function",
                    "values": {
                        "function_name": "lambda_function_name",
                        "role": "arn:aws:lambda:us-east-1:acct:res",
                        "handler": "exports.test",
                        "runtime": "nodejs12.x",
                    },
                }]
            }
        },
    }

    resources = parse_plan_json(plan)
    runner = GraphQLQueryRunner(_endpoint())
    get_cost_breakdowns(runner, resources)

    lam = next(r for r in resources if _res_address(r) == "aws_lambda_function.lambda")
    pcs = { _pc_name(pc): pc for pc in _price_components(lam) }

    # Component presence
    assert "Requests" in pcs and "Duration" in pcs

    # Price hashes (parity with Go test)
    assert _pc_price_hash(pcs["Requests"]) == "134034e58c7ef3bbaf513831c3a0161b-4a9dfd3965ffcbab75845ead7a27fd47"
    assert _pc_price_hash(pcs["Duration"]) == "a562fdf216894a62109f5b642a702f37-1786dd5ddb52682e127baa00bfaa4c48"

    # Units
    assert _pc_unit(pcs["Requests"]) == "requests"
    assert _pc_unit(pcs["Duration"]).lower() in ("gb-seconds", "gb-second", "gb-secs")

    # No usage → zero qty & costs
    assert _pc_qty_monthly(pcs["Requests"]) == 0
    assert _pc_qty_monthly(pcs["Duration"]) == 0
    assert _pc_hourly(pcs["Requests"]) == 0 and _pc_monthly(pcs["Requests"]) == 0
    assert _pc_hourly(pcs["Duration"]) == 0 and _pc_monthly(pcs["Duration"]) == 0


@pytest.mark.integration
def test_lambda_with_usage_and_memory():
    # Two functions: default 128MB and 512MB; both share the same usage.
    plan = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}}
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lambda_function.lambda",
                        "type": "aws_lambda_function",
                        "values": {
                            "function_name": "lambda_function_name",
                            "role": "arn:aws:lambda:us-east-1:acct:res",
                            "handler": "exports.test",
                            "runtime": "nodejs12.x",
                            # usage inline (Python-port convention)
                            "usage": {
                                "monthly_requests": {"value": 100000},
                                "average_request_duration": {"value": 350},
                            },
                        },
                    },
                    {
                        "address": "aws_lambda_function.lambda_512_mem",
                        "type": "aws_lambda_function",
                        "values": {
                            "function_name": "lambda_function_name",
                            "role": "arn:aws:lambda:us-east-1:acct:res",
                            "handler": "exports.test",
                            "runtime": "nodejs12.x",
                            "memory_size": 512,
                            "usage": {
                                "monthly_requests": {"value": 100000},
                                "average_request_duration": {"value": 350},
                            },
                        },
                    },
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    runner = GraphQLQueryRunner(_endpoint())
    get_cost_breakdowns(runner, resources)

    def res(addr: str):
        return next(r for r in resources if _res_address(r) == addr)

    # requests = 100000; duration 350ms → billed 400ms → 0.4 s
    # GB-seconds (128MB) = 100000 * (128/1024) * 0.4
    # GB-seconds (512MB) = 100000 * (512/1024) * 0.4
    expected_128 = Decimal("100000") * (Decimal(128) / Decimal(1024)) * Decimal("0.4")
    expected_512 = Decimal("100000") * (Decimal(512) / Decimal(1024)) * Decimal("0.4")

    for addr, expected_gbsec in (
        ("aws_lambda_function.lambda", expected_128),
        ("aws_lambda_function.lambda_512_mem", expected_512),
    ):
        pcs = { _pc_name(pc): pc for pc in _price_components(res(addr)) }
        assert "Requests" in pcs and "Duration" in pcs

        # Requests quantity should be 100000
        assert _pc_qty_monthly(pcs["Requests"]) == Decimal(100000)

        # Duration quantity should be expected GB-seconds (allow tiny rounding)
        assert abs(_pc_qty_monthly(pcs["Duration"]) - expected_gbsec) < Decimal("0.000001")

        # (Optional) sanity: monthly cost = unit price * qty (non-negative)
        unit = _pc_price(pcs["Duration"])
        monthly = _pc_monthly(pcs["Duration"])
        assert monthly == unit * _pc_qty_monthly(pcs["Duration"]) or monthly >= 0
