"""
GraphQL query build/run utilities.

- GraphQLQueryRunner with an explicit endpoint.
- Batches queries for a resource and its sub-resources.
- Returns a map keyed by (resource -> price_component -> result).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Dict, List, Tuple, Any
import logging

from plancosts.base.filters import Filter
from plancosts.base.resource import Resource, PriceComponent
from plancosts.config import PRICE_LIST_API_ENDPOINT


class GraphQLQueryRunner:
    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or PRICE_LIST_API_ENDPOINT).rstrip("/")

    def run_queries(self, resource: Resource) -> Dict[Resource, Dict[PriceComponent, Any]]:
        keys, queries = self._batch(resource)
        logging.debug("Getting pricing details from %s for %s", self.endpoint, resource.address())
        results = self._get_query_results(queries) if queries else []
        return self._unpack(keys, results)

    def _build_query(self, filters: List[Filter]) -> Dict[str, Any]:
        return {
            "query": (
                "query($filter: Filter){ "
                "products(filter: $filter){ "
                "onDemandPricing{ priceDimensions{ pricePerUnit{ USD } }}}}"
            ),
            "variables": {
                "filter": {
                    "attributes": [
                        {"key": f.key, "operation": f.operation, "value": f.value}
                        for f in (filters or [])
                    ]
                }
            },
        }

    def _get_query_results(self, queries: List[Dict[str, Any]]) -> List[Any]:
        if not queries:
            return []
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(queries).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError):
            return []
        except Exception:
            return []

    def _batch(self, resource: Resource) -> Tuple[List[Tuple[Resource, PriceComponent]], List[Dict[str, Any]]]:
        keys: List[Tuple[Resource, PriceComponent]] = []
        queries: List[Dict[str, Any]] = []

        for pc in resource.price_components():
            keys.append((resource, pc))
            queries.append(self._build_query(pc.filters()))

        for sub in resource.sub_resources():
            for pc in sub.price_components():
                keys.append((sub, pc))
                queries.append(self._build_query(pc.filters()))

        return keys, queries

    def _unpack(
        self,
        keys: List[Tuple[Resource, PriceComponent]],
        results: List[Any],
    ) -> Dict[Resource, Dict[PriceComponent, Any]]:
        out: Dict[Resource, Dict[PriceComponent, Any]] = {}
        for i, res in enumerate(results):
            r, pc = keys[i]
            out.setdefault(r, {})[pc] = res
        return out


def extract_price_from_result(result: Any) -> str:
    try:
        return result["data"]["products"][0]["onDemandPricing"][0]["priceDimensions"][0]["pricePerUnit"]["USD"]
    except Exception:
        return "0"
