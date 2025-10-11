# plancosts/costs/query.py
from __future__ import annotations

import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.resource.resource import PriceComponent, Resource

# ---------------------------
# Public types (Go parity)
# ---------------------------

GraphQLQuery = Dict[str, Any]
ResourceQueryResultMap = Dict[Resource, Dict[PriceComponent, Any]]


# ---------------------------
# Helpers
# ---------------------------

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
    Make sure we always query On-Demand prices the same way as the Go code:

    - ONLY set priceFilter.purchaseOption = "on_demand".
    - DO NOT inject product-level attributeFilters with marketoption/OnDemand
      (that is a PRICE term, not a PRODUCT attribute).

    Never override other filters provided by the price component.
    """
    # price_filter: copy and default purchaseOption
    prf: dict = {}
    if isinstance(price_filter, dict):
        prf.update(price_filter)
    prf.setdefault("purchaseOption", "on_demand")

    # product_filter: pass-through (copy)
    pf: dict = {}
    if isinstance(product_filter, dict):
        pf.update(product_filter)

    # Strip accidental product-level "marketoption" filters if present
    attrs = pf.get("attributeFilters")
    if isinstance(attrs, list):
        pf["attributeFilters"] = [
            a for a in attrs
            if not (isinstance(a, dict) and a.get("key") == "marketoption")
        ]

    return pf, prf


def _prefer_nonzero_first(payload: Any) -> Any:
    """
    In-place normalize a single GraphQL response payload by reordering each
    product.prices array so that the first non-zero USD price (if any) is first.
    """
    try:
        products = (payload or {}).get("data", {}).get("products", [])
        if not isinstance(products, list):
            return payload

        for p in products:
            prices = p.get("prices")
            if not isinstance(prices, list) or not prices:
                continue

            # Find first price with USD > 0
            idx = -1
            for i, pr in enumerate(prices):
                try:
                    usd = pr.get("USD")
                    val = Decimal(str(usd))
                    if val > 0:
                        idx = i
                        break
                except (InvalidOperation, AttributeError, TypeError):
                    continue

            # Move the first non-zero to front
            if idx > 0:
                prices.insert(0, prices.pop(idx))
    except Exception:
        # Never break the caller due to normalization
        pass
    return payload


def _normalize_batch_results(results: Any) -> List[Any]:
    """
    Ensure we always return a list of per-query results,
    and normalize each by preferring non-zero prices first.
    """
    if isinstance(results, list):
        return [_prefer_nonzero_first(r) for r in results]
    if isinstance(results, dict):
        return [_prefer_nonzero_first(results)]
    return []


# ---------------------------
# Query Runner
# ---------------------------

class GraphQLQueryRunner:
    """
    Python equivalent of Go's costs.GraphQLQueryRunner.

    - Batches all per-price-component queries for a resource (including all
      descendant sub-resources) into one HTTP POST to the GraphQL endpoint.
    - Falls back to per-query POST if the batch parse/request fails (so a single
      bad query doesn't break the whole run).
    - Returns a map keyed by (Resource, PriceComponent) to parsed results.
    """

    def __init__(self, endpoint: str | None = None) -> None:
        # Expect the fully-qualified /graphql endpoint in config.
        self.endpoint = (endpoint or PRICE_LIST_API_ENDPOINT).rstrip("/")

    # Go-style name (kept for parity with callers)
    def RunQueries(self, resource: Resource) -> ResourceQueryResultMap:
        query_keys, queries = self._batchQueries(resource)

        logging.debug(
            "Getting pricing details from %s for %s",
            self.endpoint,
            resource.address(),
        )
        query_results = self._getQueryResults(queries)
        return self._unpackQueryResults(query_keys, query_results)

    # Python-friendly alias
    def run_queries(self, resource: Resource) -> ResourceQueryResultMap:
        return self.RunQueries(resource)

    # ---------- internals ----------

    def _buildQuery(
        self,
        product_filter: Any,  # dict | None
        price_filter: Any,    # dict | None
    ) -> GraphQLQuery:
        # Normalize filters (ensure on_demand, never leak price terms into product attrs)
        pf, prf = _normalize_filters(
            product_filter if isinstance(product_filter, dict) else None,
            price_filter if isinstance(price_filter, dict) else None,
        )

        variables: Dict[str, Any] = {
            "productFilter": pf,   # never null
            "priceFilter": prf,    # always has purchaseOption
        }

        # Verbose debug (compact but readable)
        logging.debug(
            "GraphQL variables: %s",
            json.dumps(variables, separators=(",", ": "))
        )

        # Mirrors the Go query shape; also fetch priceHash for traceability
        query = """
        query($productFilter: ProductFilter!, $priceFilter: PriceFilter) {
          products(filter: $productFilter) {
            prices(filter: $priceFilter) {
              USD
              priceHash
            }
          }
        }
        """
        return {"query": query, "variables": variables}

    def _post(self, payload: Any) -> Any:
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # A short default timeout prevents hanging if the local API is down
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)

    def _getQueryResults(self, queries: List[GraphQLQuery]) -> List[Any]:
        """
        Try a single batched POST first (array of queries).
        If that fails or returns a single object, fall back to one-by-one.
        Log GraphQL "errors" arrays if present.
        """
        def _log_gql_errors(payload: Any) -> None:
            try:
                errs = payload.get("errors")
                if errs:
                    logging.error("GraphQL encountered errors:\n%s", json.dumps(errs))
            except Exception:
                pass

        # 1) Batch
        try:
            parsed = self._post(queries)
            if isinstance(parsed, list):
                for p in parsed:
                    if isinstance(p, dict):
                        _log_gql_errors(p)
                return _normalize_batch_results(parsed)
            if isinstance(parsed, dict):
                _log_gql_errors(parsed)
                return _normalize_batch_results(parsed)
        except (URLError, HTTPError) as e:
            logging.debug(
                "Batched GraphQL request failed (%s); falling back to single requests.",
                e,
            )
        except Exception as e:
            logging.debug(
                "Batched GraphQL parse error (%s); falling back to single requests.",
                e,
            )

        # 2) One-by-one fallback
        results: List[Any] = []
        for q in queries:
            try:
                r = self._post(q)
                if isinstance(r, dict):
                    _log_gql_errors(r)
                results.append(_prefer_nonzero_first(r))
            except Exception as e:
                logging.error("GraphQL single request failed: %s", e)
                # Return a harmless empty payload for this query
                results.append({"data": {"products": []}})
        return results

    def _batchQueries(
        self,
        resource: Resource,
    ) -> Tuple[List[Tuple[Resource, PriceComponent]], List[GraphQLQuery]]:
        """
        Build one query per PriceComponent for:
          - the top-level resource
          - all descendant sub-resources (flattened)
        Keep a parallel list of (resource, priceComponent) keys so we can
        re-associate the N-th response with the N-th query.
        """
        query_keys: List[Tuple[Resource, PriceComponent]] = []
        queries: List[GraphQLQuery] = []

        # Top-level price components
        for pc in resource.price_components():
            query_keys.append((resource, pc))
            queries.append(self._buildQuery(pc.product_filter(), pc.price_filter()))

        # All descendant sub-resources
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
        """
        Rebuild: { resource: { priceComponent: result } }
        Note: if the server returned more results than keys, extras are ignored.
        """
        out: ResourceQueryResultMap = {}
        for i, result in enumerate(query_results):
            if i >= len(query_keys):
                break
            r, pc = query_keys[i]
            out.setdefault(r, {})[pc] = result
        return out


# ---------------------------
# Convenience extractor
# ---------------------------

def extract_price_usd(result: Any) -> str:
    """
    Helper (useful in tests): pull USD out of the response:
      data.products[0].prices[0].USD
    Returns "0" on any shape/lookup issue.
    """
    try:
        return result["data"]["products"][0]["prices"][0]["USD"]
    except Exception:
        return "0"
