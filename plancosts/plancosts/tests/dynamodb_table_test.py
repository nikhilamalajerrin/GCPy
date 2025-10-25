from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns


# ---------- tiny helpers (resource-oriented, no breakdown wrapper) ----------

def _addr(res) -> str:
    if hasattr(res, "address") and callable(res.address):
        return res.address()
    if hasattr(res, "Address") and callable(res.Address):
        return res.Address()
    return getattr(res, "address", "<resource>")


def _subresources(res) -> List[Any]:
    if hasattr(res, "sub_resources") and callable(res.sub_resources):
        return list(res.sub_resources() or [])
    if hasattr(res, "SubResources") and callable(res.SubResources):
        return list(res.SubResources() or [])
    return list(getattr(res, "sub_resources", []) or [])


def _pcs(res) -> List[Any]:
    if hasattr(res, "price_components") and callable(res.price_components):
        return list(res.price_components() or [])
    if hasattr(res, "PriceComponents") and callable(res.PriceComponents):
        return list(res.PriceComponents() or [])
    return list(getattr(res, "cost_components", []) or [])


def _pc_name(pc) -> str:
    if hasattr(pc, "name") and callable(pc.name):
        return pc.name()
    if hasattr(pc, "Name") and callable(pc.Name):
        return pc.Name()
    return getattr(pc, "name", "<component>")


def _pc_price(pc) -> Decimal:
    if hasattr(pc, "Price") and callable(pc.Price):
        return Decimal(str(pc.Price()))
    return Decimal(str(getattr(pc, "price", "0")))


def _pc_hourly(pcc) -> Decimal:
    if hasattr(pcc, "HourlyCost") and callable(pcc.HourlyCost):
        return Decimal(str(pcc.HourlyCost()))
    return Decimal(str(getattr(pcc, "hourly_cost", "0")))


def _pc_pricehash(pcc) -> Optional[str]:
    if hasattr(pcc, "PriceHash") and callable(pcc.PriceHash):
        return pcc.PriceHash()
    if hasattr(pcc, "price_hash"):
        v = getattr(pcc, "price_hash")
        return v() if callable(v) else v
    pc = getattr(pcc, "price_component", None)
    if pc is not None:
        if hasattr(pc, "PriceHash") and callable(pc.PriceHash):
            return pc.PriceHash()
        if hasattr(pc, "price_hash"):
            vv = getattr(pc, "price_hash")
            return vv() if callable(vv) else vv
    return None


def _wrap_pccs(res) -> List[Any]:
    pccs = getattr(res, "price_component_costs", None)
    if pccs:
        return list(pccs)

    out = []
    for pc in _pcs(res):
        class _PCC:
            price_component = pc
            def HourlyCost(self):
                return getattr(pc, "hourly_cost", _pc_price(pc))
            @property
            def hourly_cost(self):
                return self.HourlyCost()
            def PriceHash(self):
                return getattr(pc, "price_hash", None)
            @property
            def price_hash(self):
                return self.PriceHash()
        out.append(_PCC())
    return out


def _find_resource(resources: List[Any], want_suffix: str) -> Optional[Any]:
    for r in resources:
        if _addr(r).endswith(want_suffix):
            return r
    return None


def _find_pcc(res_or_pcc_list: Any, name: str):
    pccs = res_or_pcc_list if isinstance(res_or_pcc_list, list) else _wrap_pccs(res_or_pcc_list)
    for pcc in pccs:
        pc = getattr(pcc, "price_component", pcc)
        if _pc_name(pc) == name:
            return pcc
    return None


def _runner():
    return GraphQLQueryRunner("http://127.0.0.1:4000/graphql")


# ---------- Test: PAY_PER_REQUEST (On-Demand) ----------

@pytest.mark.integration
def test_dynamodb_table_on_demand_with_replicas():
    plan: Dict[str, Any] = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
            "root_module": {
                "resources": [
                    {
                        "address": "aws_dynamodb_table.my_dynamodb_table",
                        "type": "aws_dynamodb_table",
                        "expressions": {
                            "name": {"constant_value": "GameScores"},
                            "billing_mode": {"constant_value": "PAY_PER_REQUEST"},
                            "hash_key": {"constant_value": "UserId"},
                            "range_key": {"constant_value": "GameTitle"},
                            "attribute": [
                                {"name": {"constant_value": "UserId"}, "type": {"constant_value": "S"}},
                                {"name": {"constant_value": "GameTitle"}, "type": {"constant_value": "S"}},
                            ],
                            "replica": [
                                {"region_name": {"constant_value": "us-east-2"}},
                                {"region_name": {"constant_value": "us-west-1"}},
                            ],
                        },
                    },
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_dynamodb_table.my_dynamodb_table",
                        "type": "aws_dynamodb_table",
                        "values": {
                            "name": "GameScores",
                            "billing_mode": "PAY_PER_REQUEST",
                            "hash_key": "UserId",
                            "range_key": "GameTitle",
                            "attribute": [
                                {"name": "UserId", "type": "S"},
                                {"name": "GameTitle", "type": "S"},
                            ],
                            "replica": [
                                {"region_name": "us-east-2"},
                                {"region_name": "us-west-1"},
                            ],
                            "_usage": {
                                "monthly_write_request_units": 3000000,
                                "monthly_read_request_units": 8000000,
                                "monthly_gb_data_storage": 230,
                                "monthly_gb_continuous_backup_storage": 2300,
                                "monthly_gb_on_demand_backup_storage": 460,
                                "monthly_gb_restore": 230,
                                "monthly_streams_read_request_units": 2000000,
                            },
                        },
                    },
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), resources)

    tbl = _find_resource(resources, "aws_dynamodb_table.my_dynamodb_table")
    assert tbl is not None, "dynamodb table not found"

    checks = [
        ("Write request unit (WRU)", "075760076246f7bf5a2b46546e49cb31-418b228ac00af0f32e1843fecbc3d141", 3000000),
        ("Read request unit (RRU)", "641aa07510d472901906f3e97cee96c4-668942c2f9f9b475e74de593d4c32257", 8000000),
        ("Data storage", "a9781acb5ee117e6c50ab836dd7285b5-ee3dd7e4624338037ca6fea0933a662f", 230),
        ("Continuous backup (PITR) storage", "b4ed90c18b808ffff191ffbc16090c8e-ee3dd7e4624338037ca6fea0933a662f", 2300),
        ("On-demand backup storage", "0e228653f3f9c663398e91a605c911bd-8753f776c1e737f1a5548191571abc76", 460),
        ("Restore data size", "38fc5fdbec6f4ef5e3bdf6967dbe1cb2-b1ae3861dc57e2db217fa83a7420374f", 230),
        ("Streams read request unit (sRRU)", "dd063861f705295d00a801050a700b3e-4a9dfd3965ffcbab75845ead7a27fd47", 2000000),
    ]

    for name, hash_, qty in checks:
        pcc = _find_pcc(tbl, name)
        assert _pc_pricehash(pcc) == hash_
        assert _pc_hourly(pcc) == _pc_price(getattr(pcc, "price_component", pcc)) * Decimal(qty)

    # replicas
    reps = _subresources(tbl)
    east2 = next((r for r in reps if _addr(r).endswith("us-east-2")), None)
    assert _pc_pricehash(_find_pcc(east2, "Replicated write request unit (rWRU)")) == "bd1c30b527edcc061037142f79c06955-cf867fc796b8147fa126205baed2922c"
    usw1 = next((r for r in reps if _addr(r).endswith("us-west-1")), None)
    assert _pc_pricehash(_find_pcc(usw1, "Replicated write request unit (rWRU)")) == "67f1a3e0472747acf74cd5e925422fbb-cf867fc796b8147fa126205baed2922c"


# ---------- Test: PROVISIONED ----------

@pytest.mark.integration
def test_dynamodb_table_provisioned_with_replicas():
    plan: Dict[str, Any] = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {"aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}},
            "root_module": {
                "resources": [
                    {
                        "address": "aws_dynamodb_table.dynamodb-table",
                        "type": "aws_dynamodb_table",
                        "expressions": {
                            "name": {"constant_value": "GameScores"},
                            "billing_mode": {"constant_value": "PROVISIONED"},
                            "read_capacity": {"constant_value": 30},
                            "write_capacity": {"constant_value": 20},
                            "hash_key": {"constant_value": "UserId"},
                            "range_key": {"constant_value": "GameTitle"},
                            "attribute": [
                                {"name": {"constant_value": "UserId"}, "type": {"constant_value": "S"}},
                                {"name": {"constant_value": "GameTitle"}, "type": {"constant_value": "S"}},
                            ],
                            "replica": [
                                {"region_name": {"constant_value": "us-east-2"}},
                                {"region_name": {"constant_value": "us-west-1"}},
                            ],
                        },
                    },
                ]
            },
        },
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_dynamodb_table.dynamodb-table",
                        "type": "aws_dynamodb_table",
                        "values": {
                            "name": "GameScores",
                            "billing_mode": "PROVISIONED",
                            "read_capacity": 30,
                            "write_capacity": 20,
                            "hash_key": "UserId",
                            "range_key": "GameTitle",
                            "attribute": [
                                {"name": "UserId", "type": "S"},
                                {"name": "GameTitle", "type": "S"},
                            ],
                            "replica": [
                                {"region_name": "us-east-2"},
                                {"region_name": "us-west-1"},
                            ],
                        },
                    },
                ]
            }
        },
    }

    resources = parse_plan_json(plan)
    get_cost_breakdowns(_runner(), resources)
    tbl = _find_resource(resources, "aws_dynamodb_table.dynamodb-table")
    assert tbl is not None, "dynamodb table resource not found"

    wcu = _find_pcc(tbl, "Write capacity unit (WCU)")
    assert _pc_pricehash(wcu) == "b90795c897109784ce65409754460c41-8931e75640eb28f75b8eeb7989b3629d"
    assert _pc_hourly(wcu) == _pc_price(getattr(wcu, "price_component", wcu)) * Decimal(20)

    rcu = _find_pcc(tbl, "Read capacity unit (RCU)")
    assert _pc_pricehash(rcu) == "30812d4142a0a73eb1efbd902581679f-bd107312a4bed8ba719b7dc8dcfdaf95"
    assert _pc_hourly(rcu) == _pc_price(getattr(rcu, "price_component", rcu)) * Decimal(30)

    reps = _subresources(tbl)
    east2 = next((r for r in reps if _addr(r).endswith("us-east-2")), None)
    assert _pc_pricehash(_find_pcc(east2, "Replicated write capacity unit (rWCU)")) == "95e8dec74ece19d8d6b9c3ff60ef881b-af782957bf62d705bf1e97f981caeab1"
    usw1 = next((r for r in reps if _addr(r).endswith("us-west-1")), None)
    assert _pc_pricehash(_find_pcc(usw1, "Replicated write capacity unit (rWCU)")) == "f472a25828ce71ef30b1aa898b7349ac-af782957bf62d705bf1e97f981caeab1"
