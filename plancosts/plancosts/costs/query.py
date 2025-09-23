# plancosts/costs/query.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.resource.filters import Filter
from plancosts.resource.resource import Resource, PriceComponent

# Types to mirror the Go code’s structure
GraphQLQuery = Dict[str, Any]
ResourceQueryResultMap = Dict[Resource, Dict[PriceComponent, Any]]


def _flatten_subresources(resource: Resource) -> List[Resource]:
    """Recursive equivalent of Go's FlattenSubResources."""
    out: List[Resource] = []
    for sub in resource.sub_resources():
        out.append(sub)
        subsubs = _flatten_subresources(sub)
        if subsubs:
            out.extend(subsubs)
    return out


class GraphQLQueryRunner:
    def __init__(self, endpoint: str | None = None) -> None:
        # Go receives the exact endpoint (often .../graphql). Preserve as-is.
        self.endpoint = (endpoint or PRICE_LIST_API_ENDPOINT).rstrip("/")

    # --- public API (Go-style name kept for parity) ---
    def RunQueries(self, resource: Resource) -> ResourceQueryResultMap:
        query_keys, queries = self._batchQueries(resource)
        logging.debug("Getting pricing details from %s for %s", self.endpoint, resource.address())
        query_results = self._getQueryResults(queries)
        return self._unpackQueryResults(query_keys, query_results)

    # Python-friendly alias
    def run_queries(self, resource: Resource) -> ResourceQueryResultMap:
        return self.RunQueries(resource)

    # --- internals mirroring Go methods ---

    def _buildQuery(self, filters: List[Filter]) -> GraphQLQuery:
        # Keep exact variable shape used by Go
        variables: Dict[str, Any] = {"filter": {"attributes": []}}
        variables["filter"]["attributes"] = [
            {
                "key": f.key,
                "value": f.value,
                **({"operation": f.operation} if getattr(f, "operation", "") else {}),
            }
            for f in (filters or [])
        ]

        query = """
        query($filter: ProductFilter!) {
          products(filter: $filter) {
            onDemandPricing {
              priceDimensions {
                unit
                pricePerUnit { USD }
              }
            }
          }
        }
        """
        return {"query": query, "variables": variables}

    def _getQueryResults(self, queries: List[GraphQLQuery]) -> List[Any]:
        results: List[Any] = []
        try:
            body = json.dumps(queries).encode("utf-8")
            req = Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw)
            # Go expects an array of GraphQL responses; accept single or array
            if isinstance(parsed, list):
                results.extend(parsed)
            elif isinstance(parsed, dict):
                results.append(parsed)
        except (URLError, HTTPError) as e:
            logging.error("GraphQL request failed: %s", e)
        except Exception as e:
            logging.error("GraphQL response parse error: %s", e)
        return results

    def _batchQueries(self, resource: Resource) -> Tuple[List[Tuple[Resource, PriceComponent]], List[GraphQLQuery]]:
        query_keys: List[Tuple[Resource, PriceComponent]] = []
        queries: List[GraphQLQuery] = []

        # Top-level price components
        for pc in resource.price_components():
            query_keys.append((resource, pc))
            queries.append(self._buildQuery(pc.filters()))

        # Recursively include ALL descendant sub-resources (Go: FlattenSubResources)
        for sub in _flatten_subresources(resource):
            for pc in sub.price_components():
                query_keys.append((sub, pc))
                queries.append(self._buildQuery(pc.filters()))

        return query_keys, queries

    def _unpackQueryResults(
        self,
        query_keys: List[Tuple[Resource, PriceComponent]],
        query_results: List[Any],
    ) -> ResourceQueryResultMap:
        out: ResourceQueryResultMap = {}
        for i, result in enumerate(query_results):
            if i >= len(query_keys):
                break
            r, pc = query_keys[i]
            out.setdefault(r, {})[pc] = result
        return out


def extract_price_usd(result: Any) -> str:
    try:
        return result["data"]["products"][0]["onDemandPricing"][0]["priceDimensions"][0]["pricePerUnit"]["USD"]
    except Exception:
        return "0"
