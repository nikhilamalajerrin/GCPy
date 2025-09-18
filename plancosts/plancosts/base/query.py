# plancosts/base/query.py
"""
GraphQL query build/run utilities for the refactored model.
- Reads endpoint from PLAN_COSTS_PRICE_LIST_API_ENDPOINT (default: http://localhost:4000/graphql)
- Batches price-component queries for a resource + its sub-resources
"""
from __future__ import annotations

import json
import os
from typing import List, Dict, Tuple, Any
import urllib.request
import urllib.error

from plancosts.base.filters import Filter
from plancosts.base.resource import Resource, PriceComponent

# Prefer config module if present; fall back to env var
_API_URL: str
try:
    from plancosts.config import CONFIG  # optional module
    _API_URL = getattr(CONFIG, "price_list_api_endpoint", None) or os.getenv(
        "PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "http://localhost:4000/graphql"
    )
except Exception:
    _API_URL = os.getenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "http://localhost:4000/graphql")


def build_query(filters: List[Filter]) -> Dict[str, Any]:
    """Build a single GraphQL query for the given filter list."""
    return {
        "query": (
            "query($filter: Filter){ "
            "products(filter: $filter){ "
            "onDemandPricing{ priceDimensions{ pricePerUnit{ USD } }}}}"
        ),
        "variables": {
            "filter": [
                {"key": f.key, "operation": f.operation, "value": f.value}
                for f in (filters or [])
            ]
        },
    }


def get_query_results(queries: List[Dict[str, Any]]) -> List[Any]:
    """POST a batch of GraphQL queries and return the list of results."""
    if not queries:
        return []
    req = urllib.request.Request(
        _API_URL,
        data=json.dumps(queries).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            # Server returns a JSON array of results (one per query)
            return json.loads(body)
    except urllib.error.URLError as e:
        # If the price API isn't running, just return empty results (prices become zero)
        # You can raise here instead if you want hard failure.
        return []
    except Exception:
        return []


def extract_price_from_result(result: Any) -> str:
    """Pull USD unit price string from a GraphQL result; '0' if missing."""
    try:
        return result["data"]["products"][0]["onDemandPricing"][0]["priceDimensions"][0]["pricePerUnit"]["USD"]
    except Exception:
        return "0"


# -------- batching --------

Key = Tuple[Resource, PriceComponent]


def _batch(resource: Resource) -> Tuple[List[Key], List[Dict[str, Any]]]:
    keys: List[Key] = []
    queries: List[Dict[str, Any]] = []

    for pc in resource.price_components():
        if pc.skip_query():
            continue
        keys.append((resource, pc))
        queries.append(build_query(pc.filters()))

    for sub in resource.sub_resources():
        for pc in sub.price_components():
            if pc.skip_query():
                continue
            keys.append((sub, pc))
            queries.append(build_query(pc.filters()))

    return keys, queries


def run_queries(resource: Resource) -> Dict[Resource, Dict[PriceComponent, Any]]:
    """Run all queries for a resource (and subs) and map results back to (resource, price-component)."""
    keys, queries = _batch(resource)
    results = get_query_results(queries) if queries else []
    out: Dict[Resource, Dict[PriceComponent, Any]] = {}
    for i, res in enumerate(results):
        r, pc = keys[i]
        out.setdefault(r, {})[pc] = res
    return out
