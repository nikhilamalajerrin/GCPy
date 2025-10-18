from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Dict, Optional, List

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------------- duck-typed helpers ----------------

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

def _addr(res) -> str:
    return _call(res, "address", "Address", "name", "Name") or "<resource>"

def _pcs(res) -> list[Any]:
    v = _call(res, "price_components", "PriceComponents", default=[])
    return list(v) if isinstance(v, Iterable) else []

def _pc_name(pc) -> str:
    return _call(pc, "name", "Name") or "<component>"

def _pc_unit(pc) -> str:
    return _call(pc, "unit", "Unit", "unit_", default="") or ""

def _pc_price(pc) -> Decimal:
    return _d(_call(pc, "Price", "price", default=0))

def _pc_hourly(pc) -> Decimal:
    return _d(_call(pc, "HourlyCost", "hourly_cost", default=0))

def _pc_monthly(pc) -> Decimal:
    return _d(_call(pc, "MonthlyCost", "monthly_cost", default=0))

def _pc_monthly_qty(pc) -> Decimal:
    q = _call(pc, "MonthlyQuantity", "monthly_quantity", "Quantity", "quantity", default=0)
    return _d(q)

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

def _runner():
    return GraphQLQueryRunner(os.getenv("PLANCOSTS_PRICE_API", "http://127.0.0.1:4000/graphql"))


# ---------------- shared plan header ----------------

BASE_CONF = {
    "format_version": "0.1",
    "terraform_version": "0.14.0",
    "configuration": {
        "provider_config": {
            "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
        },
        "root_module": {},
    },
}


# ---------------- tests mirroring Go ----------------

@pytest.mark.integration
def test_db_instance_matrix():
    # Mirrors TestDBInstance
    planned_resources: List[Dict[str, Any]] = [
        # mysql
        {
            "address": "aws_db_instance.mysql",
            "type": "aws_db_instance",
            "values": {"engine": "mysql", "instance_class": "db.t3.large"},
        },
        # mysql-allocated-storage (20 GB)
        {
            "address": "aws_db_instance.mysql-allocated-storage",
            "type": "aws_db_instance",
            "values": {"engine": "mysql", "instance_class": "db.t3.large", "allocated_storage": 20},
        },
        # mysql-multi-az (30 GB)
        {
            "address": "aws_db_instance.mysql-multi-az",
            "type": "aws_db_instance",
            "values": {"engine": "mysql", "instance_class": "db.t3.large", "multi_az": True, "allocated_storage": 30},
        },
        # mysql-magnetic (40 GB)
        {
            "address": "aws_db_instance.mysql-magnetic",
            "type": "aws_db_instance",
            "values": {"engine": "mysql", "instance_class": "db.t3.large", "storage_type": "standard", "allocated_storage": 40},
        },
        # mysql-iops (50 GB, 500 IOPS)
        {
            "address": "aws_db_instance.mysql-iops",
            "type": "aws_db_instance",
            "values": {"engine": "mysql", "instance_class": "db.t3.large", "storage_type": "io1", "allocated_storage": 50, "iops": 500},
        },
    ]

    plan = {
        **BASE_CONF,
        "planned_values": {"root_module": {"resources": planned_resources}},
    }

    resources = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), resources)

    def _get(name: str):
        r = next((r for r in resources if _addr(r) == name), None)
        assert r is not None, f"{name} not parsed/priced"
        return r

    single_az_hash = "04a2cf31c0b8bf8623b1c4bd96856d49-d2c98780d7b6e36641b521f1f8145c6f"

    # mysql
    r = _get("aws_db_instance.mysql")
    comps = { _pc_name(pc): pc for pc in _pcs(r) }
    pc_inst = comps["Database instance"]
    assert _pc_price_hash(pc_inst) == single_az_hash
    assert _pc_hourly(pc_inst) == _pc_price(pc_inst)  # qty 1/hour

    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "b7b7cfbe7ec1bded9a474fff7123b34f-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 0
    assert _pc_monthly(pc_storage) == 0

    # mysql-allocated-storage
    r = _get("aws_db_instance.mysql-allocated-storage")
    comps = { _pc_name(pc): pc for pc in _pcs(r) }
    assert _pc_price_hash(comps["Database instance"]) == single_az_hash
    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "b7b7cfbe7ec1bded9a474fff7123b34f-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 20
    assert _pc_monthly(pc_storage) == _pc_price(pc_storage) * Decimal(20)

    # mysql-multi-az
    r = _get("aws_db_instance.mysql-multi-az")
    comps = { _pc_name(pc): pc for pc in _pcs(r) }
    pc_inst = comps["Database instance"]
    assert _pc_price_hash(pc_inst) == "6533699ad0fd39e396567de86c73917b-d2c98780d7b6e36641b521f1f8145c6f"
    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "2ec5ef73cbd5ca537c967fff828f39fe-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 30
    assert _pc_monthly(pc_storage) == _pc_price(pc_storage) * Decimal(30)

    # mysql-magnetic
    r = _get("aws_db_instance.mysql-magnetic")
    comps = { _pc_name(pc): pc for pc in _pcs(r) }
    assert _pc_price_hash(comps["Database instance"]) == single_az_hash
    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "87a57c551b26e3c6114e5034536dd82c-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 40
    assert _pc_monthly(pc_storage) == _pc_price(pc_storage) * Decimal(40)

    # mysql-iops
    r = _get("aws_db_instance.mysql-iops")
    comps = { _pc_name(pc): pc for pc in _pcs(r) }
    assert _pc_price_hash(comps["Database instance"]) == single_az_hash
    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "49c604321c7ca45d46173de5bdcbe1d9-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 50
    assert _pc_monthly(pc_storage) == _pc_price(pc_storage) * Decimal(50)

    pc_iops = comps["Database storage IOPS"]
    assert _pc_price_hash(pc_iops) == "feb9c53577f5beba555ef9a78d59a160-9c483347596633f8cf3ab7fdd5502b78"
    assert _pc_monthly_qty(pc_iops) == 500
    assert _pc_monthly(pc_iops) == _pc_price(pc_iops) * Decimal(500)


@pytest.mark.integration
def test_db_instance_all_engines():
    # Mirrors TestDBInstance_allEngines (updated: remove deprecated Oracle SE/SE1)
    expected = [
    ("aurora",              "db.t3.small",  "edddc435c5a03ea1cb0d97b904306d77-d2c98780d7b6e36641b521f1f8145c6f"),
    ("aurora-mysql",        "db.t3.small",  "edddc435c5a03ea1cb0d97b904306d77-d2c98780d7b6e36641b521f1f8145c6f"),
    ("aurora-postgresql",   "db.t3.large",  "c02a325181f4b5bc43827fded2393de9-d2c98780d7b6e36641b521f1f8145c6f"),
    ("mariadb",             "db.t3.large",  "c26e17848bf2a0594017d471892782c2-d2c98780d7b6e36641b521f1f8145c6f"),
    ("mysql",               "db.t3.large",  "04a2cf31c0b8bf8623b1c4bd96856d49-d2c98780d7b6e36641b521f1f8145c6f"),
    ("postgres",            "db.t3.large",  "4aed0c16438fe1bce3400ded9c81e46e-d2c98780d7b6e36641b521f1f8145c6f"),
    ("oracle-se2",          "db.t3.large",  "7839bf8f2edb4a8ac8cc236fc042e0c7-d2c98780d7b6e36641b521f1f8145c6f"),
    ("oracle-ee",           "db.t3.large",  "e11ffc928ba6c26619f3b6426420b6ec-d2c98780d7b6e36641b521f1f8145c6f"),
    ("sqlserver-ex",        "db.t3.large",  "f13c7b2b683a29ba8c512253d27c92a4-d2c98780d7b6e36641b521f1f8145c6f"),
    ("sqlserver-web",       "db.t3.large",  "7a5ab0c93fc3b3e49672cb3a1e6d7c16-d2c98780d7b6e36641b521f1f8145c6f"),
    ("sqlserver-se",        "db.m5.xlarge", "24dc9e9f6ca1eec2578b2db58dd5332a-d2c98780d7b6e36641b521f1f8145c6f"),
    ("sqlserver-ee",        "db.m5.xlarge", "b117119f12e72674a8748f43d7a2a70c-d2c98780d7b6e36641b521f1f8145c6f"),
]


    resources: List[Dict[str, Any]] = []
    for eng, iclass, _ in expected:
        resources.append({
            "address": f"aws_db_instance.{eng}",
            "type": "aws_db_instance",
            "values": {"engine": eng, "instance_class": iclass},
        })

    plan = {**BASE_CONF, "planned_values": {"root_module": {"resources": resources}}}
    rs = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), rs)

    for eng, _iclass, price_hash in expected:
        r = next((x for x in rs if _addr(x) == f"aws_db_instance.{eng}"), None)
        assert r is not None, f"{eng} not parsed/priced"
        comps = { _pc_name(pc): pc for pc in _pcs(r) }
        pc_inst = comps.get("Database instance")
        assert pc_inst is not None, f"{eng}: missing Database instance component"
        assert _pc_price_hash(pc_inst) == price_hash, f"{eng}: expected {price_hash}, got {_pc_price_hash(pc_inst)}"

        # Storage present with zero quantity (hash constant in Go tests)
        pc_storage = comps.get("Database storage")
        assert pc_storage is not None, f"{eng}: missing Database storage"
        assert _pc_price_hash(pc_storage) == "b7b7cfbe7ec1bded9a474fff7123b34f-ee3dd7e4624338037ca6fea0933a662f"
        assert _pc_monthly_qty(pc_storage) == 0

@pytest.mark.integration
def test_db_instance_byol():
    # Mirrors TestDBInstance_byol (updated: use Oracle SE2 BYOL)
    plan = {
        **BASE_CONF,
        "planned_values": {
            "root_module": {
                "resources": [{
                    "address": "aws_db_instance.oracle-se2",
                    "type": "aws_db_instance",
                    "values": {
                        "engine": "oracle-se2",
                        "instance_class": "db.t3.large",
                        "license_model": "bring-your-own-license",
                    },
                }]
            }
        },
    }

    rs = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), rs)

    r = next((x for x in rs if _addr(x) == "aws_db_instance.oracle-se2"), None)
    assert r is not None
    comps = { _pc_name(pc): pc for pc in _pcs(r) }

    pc_inst = comps["Database instance"]
    # Current BYOL hash for Oracle SE2 db.t3.large Single-AZ
    assert _pc_price_hash(pc_inst) == "61e3a81d0f366e230c2f0ed3e659a715-d2c98780d7b6e36641b521f1f8145c6f"
    assert _pc_hourly(pc_inst) == _pc_price(pc_inst)

    pc_storage = comps["Database storage"]
    assert _pc_price_hash(pc_storage) == "b7b7cfbe7ec1bded9a474fff7123b34f-ee3dd7e4624338037ca6fea0933a662f"
    assert _pc_monthly_qty(pc_storage) == 0
