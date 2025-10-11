# plancosts/costs/query.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.resource.resource import Resource, PriceComponent

# Type aliases for parity with the Go code
GraphQLQuery = Dict[str, Any]
ResourceQueryResultMap = Dict[Resource, Dict[PriceComponent, Any]]


def _flatten_subresources(resource: Resource) -> List[Resource]:
    """Recursive equivalent of Go's resource.FlattenSubResources."""
    out: List[Resource] = []
    for sub in resource.sub_resources():
        out.append(sub)
        out.extend(_flatten_subresources(sub))
    return out


def _normalize_filters(
    product_filter: dict | None,
    price_filter: dict | None,
) -> tuple[dict, dict]:
    """
    Ensure we query On-Demand prices correctly:

    - ONLY set priceFilter.purchaseOption = "on_demand".
    - DO NOT inject productFilter.attributeFilters = [{"key":"marketoption","value":"OnDemand"}]
      since 'marketoption' is a PRICE term, not a PRODUCT attribute in the schema.

    Never remove/override other filters provided by the price component.
    """
    # price_filter
    prf: dict = {}
    if isinstance(price_filter, dict):
        prf.update(price_filter)
    prf.setdefault("purchaseOption", "on_demand")

    # product_filter (pass-through)
    pf: dict = {}
    if isinstance(product_filter, dict):
        pf.update(product_filter)

    # If a caller mistakenly added product-level "marketoption", strip it quietly to avoid empty matches.
    attrs = pf.get("attributeFilters")
    if isinstance(attrs, list):
        pf["attributeFilters"] = [
            a for a in attrs
            if not (isinstance(a, dict) and a.get("key") == "marketoption")
        ]

    return pf, prf


class GraphQLQueryRunner:
    def __init__(self, endpoint: str | None = None) -> None:
        # Expect fully-qualified /graphql endpoint (our config ensures that)
        self.endpoint = (endpoint or PRICE_LIST_API_ENDPOINT).rstrip("/")

    # Go-style name kept for callers that expect it
    def RunQueries(self, resource: Resource) -> ResourceQueryResultMap:
        query_keys, queries = self._batchQueries(resource)
        logging.debug("Getting pricing details from %s for %s", self.endpoint, resource.address())
        query_results = self._getQueryResults(queries)
        return self._unpackQueryResults(query_keys, query_results)

    # Python-friendly alias
    def run_queries(self, resource: Resource) -> ResourceQueryResultMap:
        return self.RunQueries(resource)

    # --- internals ---

    def _buildQuery(
        self,
        product_filter: Any,  # dict | None
        price_filter: Any,    # dict | None
    ) -> GraphQLQuery:
        # Normalize filters (ensure on-demand; never push price terms into product attrs)
        pf, prf = _normalize_filters(
            product_filter if isinstance(product_filter, dict) else None,
            price_filter if isinstance(price_filter, dict) else None,
        )

        variables: Dict[str, Any] = {
            "productFilter": pf,   # never null
            "priceFilter": prf,    # always has purchaseOption
        }

        # Verbose introspection
        logging.debug("GraphQL variables: %s", json.dumps(variables, separators=(",", ": ")))

        # Matches the Go commit’s query shape
        query = """
        query($productFilter: ProductFilter!, $priceFilter: PriceFilter) {
          products(filter: $productFilter) {
            prices(filter: $priceFilter) {
              USD
            }
          }
        }
        """
        return {"query": query, "variables": variables}

    def _post(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)

    def _getQueryResults(self, queries: List[GraphQLQuery]) -> List[Any]:
        def _log_gql_errors(payload: Any) -> None:
            try:
                errs = payload.get("errors")
                if errs:
                    logging.error("GraphQL encountered errors:\n%s", json.dumps(errs))
            except Exception:
                pass

        # 1) Try batch first
        try:
            parsed = self._post(queries)
            if isinstance(parsed, list):
                for p in parsed:
                    if isinstance(p, dict):
                        _log_gql_errors(p)
                return parsed
            if isinstance(parsed, dict):
                _log_gql_errors(parsed)
                return [parsed]
        except (URLError, HTTPError) as e:
            logging.debug("Batched GraphQL request failed (%s); falling back to single requests.", e)
        except Exception as e:
            logging.debug("Batched GraphQL parse error (%s); falling back to single requests.", e)

        # 2) Fallback: one-by-one so a single bad query doesn't sink the whole run
        results: List[Any] = []
        for q in queries:
            try:
                r = self._post(q)
                if isinstance(r, dict):
                    _log_gql_errors(r)
                results.append(r)
            except Exception as e:
                logging.error("GraphQL single request failed: %s", e)
                # return a harmless empty payload
                results.append({"data": {"products": []}})
        return results

    def _batchQueries(self, resource: Resource) -> Tuple[List[Tuple[Resource, PriceComponent]], List[GraphQLQuery]]:
        query_keys: List[Tuple[Resource, PriceComponent]] = []
        queries: List[GraphQLQuery] = []

        # Top-level PCs
        for pc in resource.price_components():
            query_keys.append((resource, pc))
            queries.append(self._buildQuery(pc.product_filter(), pc.price_filter()))

        # All descendant sub-resources (flatten)
        for sub in _flatten_subresources(resource):
            for pc in sub.price_components():
                query_keys.append((sub, pc))
                queries.append(self._buildQuery(pc.product_filter(), pc.price_filter()))

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
    """
    Helper (used by tests or callers) to pull USD out of the new response:
      data.products[0].prices[0].USD
    """
    try:
        return result["data"]["products"][0]["prices"][0]["USD"]
    except Exception:
        return "0"
