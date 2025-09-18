"""
GraphQL query build/run utilities for the refactored model.
"""
from __future__ import annotations
import os, json
from typing import List, Dict, Tuple, Any
import urllib.request
from plancosts.base.filters import Filter
from plancosts.base.resource import Resource, PriceComponent

API_URL = os.getenv("PLANCOSTS_API_URL", "http://127.0.0.1:4000/")

def build_query(filters: List[Filter]) -> Dict[str, Any]:
    # Flatten filters to the shape the mock server expects; the actual schema
    # is not enforced here, we just pass filters through.
    return {
        "query": "query($filter: Filter){ products(filter: $filter){ onDemandPricing{ priceDimensions{ pricePerUnit{ USD } }}}}",
        "variables": {
            "filter": [{ "key": f.key, "operation": f.operation, "value": f.value } for f in (filters or [])]
        }
    }

def get_query_results(queries: List[Dict[str, Any]]) -> List[Any]:
    if not queries:
        return []
    req = urllib.request.Request(API_URL, data=json.dumps(queries).encode("utf-8"), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def extract_price_from_result(result: Any) -> str:
    try:
        return result["data"]["products"][0]["onDemandPricing"][0]["priceDimensions"][0]["pricePerUnit"]["USD"]
    except Exception:
        return "0"

# Batch & run
Key = Tuple[Resource, PriceComponent]

def _batch(resource: Resource) -> Tuple[List[Key], List[Dict[str, Any]]]:
    keys: List[Key] = []
    queries: List[Dict[str, Any]] = []
    for pc in resource.price_components():
        if pc.skip_query(): continue
        keys.append((resource, pc))
        queries.append(build_query(pc.filters()))
    for sub in resource.sub_resources():
        for pc in sub.price_components():
            if pc.skip_query(): continue
            keys.append((sub, pc))
            queries.append(build_query(pc.filters()))
    return keys, queries

def run_queries(resource: Resource) -> Dict[Resource, Dict[PriceComponent, Any]]:
    keys, queries = _batch(resource)
    results = get_query_results(queries) if queries else []
    out: Dict[Resource, Dict[PriceComponent, Any]] = {}
    for i, res in enumerate(results):
        r, pc = keys[i]
        out.setdefault(r, {})[pc] = res
    return out
