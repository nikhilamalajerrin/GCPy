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
    """
    Normalize to 'price component costs' containers.
    If your pricing layer already exposes .price_component_costs, use it.
    Otherwise build a thin wrapper so _pc_hourly/_pc_pricehash keep working.
    """
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


# ---------- the test (parity with Go expectations, adapted to your dataset) ----------

@pytest.mark.integration
def test_dynamodb_table_provisioned_with_replicas():
    plan: Dict[str, Any] = {
        "format_version": "0.1",
        "terraform_version": "0.14.0",
        "configuration": {
            "provider_config": {
                "aws": {"expressions": {"region": {"constant_value": "us-east-1"}}}
            },
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

    # Parse the plan and see what we get
    resources = parse_plan_json(plan)
    
    # DEBUG: Print information about what was parsed
    print(f"\nDEBUG: Number of resources parsed: {len(resources)}")
    print(f"DEBUG: Type of resources: {type(resources)}")
    
    if resources:
        for i, res in enumerate(resources):
            print(f"\nDEBUG: Resource {i}:")
            print(f"  Type: {type(res)}")
            print(f"  Address: {_addr(res)}")
            print(f"  Has 'address' attr: {hasattr(res, 'address')}")
            print(f"  Dir: {[attr for attr in dir(res) if not attr.startswith('_')][:10]}")  # First 10 attrs
            
            # Try to get more details about the resource
            if hasattr(res, '__dict__'):
                print(f"  __dict__ keys: {list(res.__dict__.keys())[:10]}")  # First 10 keys
    else:
        print("DEBUG: Resources list is empty!")
    
    # Also try to see if parse_plan_json is expecting different input structure
    # Try passing just the planned_values section
    print("\n--- Trying with just planned_values ---")
    resources2 = parse_plan_json(plan["planned_values"])
    print(f"DEBUG: Resources from planned_values: {len(resources2) if resources2 else 0}")
    
    # Continue with the original test to see where it fails
    # This prices in-place; we don't need the return object.
    get_cost_breakdowns(_runner(), resources)
    
    # Find the table resource directly (no breakdown wrapper)
    tbl = _find_resource(resources, "aws_dynamodb_table.dynamodb-table")
    assert tbl is not None, "dynamodb table resource not found"

    # ---- Top-level components: WCU/RCU ----
    wcu = _find_pcc(tbl, "Write capacity unit (WCU)")
    assert wcu is not None, "missing WCU component"
    price_wcu = _pc_price(getattr(wcu, "price_component", wcu))
    hourly_wcu = _pc_hourly(wcu)
    assert hourly_wcu == price_wcu * Decimal(20), f"WCU hourly mismatch: got {hourly_wcu}, want {price_wcu} * 20"

    rcu = _find_pcc(tbl, "Read capacity unit (RCU)")
    assert rcu is not None, "missing RCU component"
    price_rcu = _pc_price(getattr(rcu, "price_component", rcu))
    hourly_rcu = _pc_hourly(rcu)
    assert hourly_rcu == price_rcu * Decimal(30), f"RCU hourly mismatch: got {hourly_rcu}, want {price_rcu} * 30"

    # ---- Replicas (sub-resources by region) ----
    reps = _subresources(tbl)

    # us-east-2
    east2 = next((r for r in reps if _addr(r).endswith("us-east-2")), None)
    assert east2 is not None, "replica us-east-2 not found"
    east2_rwcu = _find_pcc(east2, "Replicated write capacity unit (rWCU)")
    assert east2_rwcu is not None, "us-east-2 rWCU missing"
    # Known price hash from your dataset
    assert _pc_pricehash(east2_rwcu) == "95e8dec74ece19d8d6b9c3ff60ef881b-af782957bf62d705bf1e97f981caeab1"
    price_e2 = _pc_price(getattr(east2_rwcu, "price_component", east2_rwcu))
    hourly_e2 = _pc_hourly(east2_rwcu)
    assert hourly_e2 == price_e2 * Decimal(20)

    # us-west-1
    usw1 = next((r for r in reps if _addr(r).endswith("us-west-1")), None)
    assert usw1 is not None, "replica us-west-1 not found"
    usw1_rwcu = _find_pcc(usw1, "Replicated write capacity unit (rWCU)")
    assert usw1_rwcu is not None, "us-west-1 rWCU missing"
    assert _pc_pricehash(usw1_rwcu) == "f472a25828ce71ef30b1aa898b7349ac-af782957bf62d705bf1e97f981caeab1"
    price_w1 = _pc_price(getattr(usw1_rwcu, "price_component", usw1_rwcu))
    hourly_w1 = _pc_hourly(usw1_rwcu)
    assert hourly_w1 == price_w1 * Decimal(20)