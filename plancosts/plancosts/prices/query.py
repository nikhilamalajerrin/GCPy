# plancosts/prices/query.py
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from plancosts.config import PRICE_LIST_API_ENDPOINT

GraphQLQuery = Dict[str, Any]


# ---------- headers: User-Agent + API key ----------
def _plancosts_env() -> str:
    v = (os.getenv("PLANCOSTS_ENV") or os.getenv("INFRACOST_ENV") or "").strip().lower()
    if v in ("test", "dev"):
        return v
    # Heuristic for tests (roughly mirrors Go's .test suffix check)
    try:
        exe = os.path.basename(os.getenv("_", ""))
        if exe.endswith(".test"):
            return "test"
    except Exception:
        pass
    return ""


def _plancosts_user_agent() -> str:
    base = "plancosts"
    try:
        # Try to read package version for UA stamping
        import importlib

        m = importlib.import_module("plancosts")
        ver = getattr(m, "__version__", "") or ""
    except Exception:
        ver = ""
    if ver:
        base = f"{base}-{ver}"
    env = _plancosts_env()
    if env:
        base = f"{base} ({env})"
    return base


def _plancosts_api_key() -> str:
    # Supports both env names
    return os.getenv("PLANCOSTS_API_KEY") or os.getenv("SELF_HOSTED_INFRACOST_API_KEY") or ""


def _prefer_nonzero_first(payload: Any) -> Any:
    """
    If a product has multiple prices, try to move the first non-zero USD price
    to index 0 so callers consistently pick a real price.
    """
    try:
        products = (payload or {}).get("data", {}).get("products", [])
        if not isinstance(products, list):
            return payload
        for p in products:
            prices = p.get("prices")
            if not isinstance(prices, list) or not prices:
                continue
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
            if idx > 0:
                prices.insert(0, prices.pop(idx))
    except Exception:
        pass
    return payload


def _normalize_batch_results(results: Any) -> List[Any]:
    if isinstance(results, list):
        return [_prefer_nonzero_first(r) for r in results]
    if isinstance(results, dict):
        return [_prefer_nonzero_first(results)]
    return []


def _extract_filter(obj: Any, method_name: str, attr_name: str) -> Any:
    """
    Try method first (provider components), then attribute (schema components),
    and call it if it's callable.
    """
    if hasattr(obj, method_name):
        fn = getattr(obj, method_name)
        try:
            return fn() if callable(fn) else fn
        except Exception:
            pass
    if hasattr(obj, attr_name):
        val = getattr(obj, attr_name)
        try:
            return val() if callable(val) else val
        except Exception:
            pass
    return None


def _product_has_marketoption_spot(pf: Any) -> bool:
    try:
        attrs = (pf or {}).get("attributeFilters") or []
        for a in attrs:
            k = (a.get("key") or "").lower()
            v = (a.get("value") or "").lower()
            if k == "marketoption" and v == "spot":
                return True
    except Exception:
        pass
    return False


def _has_marketoption(vars_obj: dict) -> bool:
    try:
        for f in (vars_obj.get("productFilter", {}).get("attributeFilters") or []):
            if isinstance(f, dict) and (f.get("key") or "").lower() == "marketoption":
                return True
    except Exception:
        pass
    return False


def _pop_marketoption_to_purchaseoption(vars_obj: dict) -> dict:
    """
    Return a new variables dict where productFilter.attributeFilters['marketoption']
    is removed and its value mapped to priceFilter.purchaseOption ('spot' / 'on_demand').
    """
    vars_new = deepcopy(vars_obj) if isinstance(vars_obj, dict) else {"productFilter": {}, "priceFilter": {}}
    pf = vars_new.get("productFilter") or {}
    prf = vars_new.get("priceFilter") or {}

    mo_val = None
    af = pf.get("attributeFilters")
    if isinstance(af, list) and af:
        new_af = []
        for f in af:
            if isinstance(f, dict) and (f.get("key") or "").lower() == "marketoption":
                mo_val = (f.get("value") or "").strip()
                # drop it from productFilter (we'll move it to priceFilter)
                continue
            new_af.append(f)
        if new_af:
            pf["attributeFilters"] = new_af
        else:
            pf.pop("attributeFilters", None)

    if mo_val:
        low = mo_val.lower()
        # IMPORTANT: use lowercase tokens that the API expects
        prf["purchaseOption"] = "spot" if low == "spot" else "on_demand"

    vars_new["productFilter"] = pf
    vars_new["priceFilter"] = prf
    return vars_new


def _normalize_filters(product_filter: Any, price_filter: Any) -> tuple[dict, dict]:
    """
    Normalize product- and price-level filters for the GraphQL endpoint.

    Rules:
      - Preserve product-level `marketoption` (OnDemand/Spot).
      - Only add price-level `purchaseOption='spot'` when product says `marketoption=Spot`.
      - Do NOT add purchaseOption by default (breaks EBS, etc.).
      - Remove legacy/empty price-level keys like `term` or empty purchaseOption.
    """
    # Product filter
    pf: dict = {}
    if isinstance(product_filter, dict):
        pf.update(product_filter)
    if "attributeFilters" in pf and not pf["attributeFilters"]:
        pf.pop("attributeFilters", None)

    # Price filter
    prf: dict = {}
    if isinstance(price_filter, dict):
        prf.update(price_filter)
    prf.pop("term", None)
    if prf.get("purchaseOption") in (None, ""):
        prf.pop("purchaseOption", None)

    # If product filter explicitly requests Spot, ensure price-level purchaseOption='spot'
    # (This makes Spot EC2 work while leaving EBS & On-Demand untouched.)
    if _product_has_marketoption_spot(pf) and "purchaseOption" not in prf:
        prf["purchaseOption"] = "spot"

    return pf, prf


class GraphQLQueryRunner:
    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or PRICE_LIST_API_ENDPOINT).rstrip("/")

    def RunQueries(self, resource: Any) -> Dict[Any, Dict[Any, Any]]:
        query_keys, queries = self._batchQueries(resource)
        logging.debug(
            "Getting pricing details from %s for %s",
            self.endpoint,
            getattr(resource, "address", lambda: "<resource>")(),
        )
        query_results = self._getQueryResults(queries)
        return self._unpackQueryResults(query_keys, query_results)

    # alias for older call sites
    run_queries = RunQueries

    def _buildQuery(self, product_filter: Any, price_filter: Any) -> GraphQLQuery:
        pf, prf = _normalize_filters(product_filter, price_filter)
        variables: Dict[str, Any] = {"productFilter": pf, "priceFilter": prf}
        logging.debug("GraphQL variables: %s", json.dumps(variables, separators=(",", ": ")))
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
        headers = {
            "Content-Type": "application/json",
            "User-Agent": _plancosts_user_agent(),
        }
        api_key = _plancosts_api_key()
        if api_key:
            headers["X-Api-Key"] = api_key
        req = Request(self.endpoint, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)

    def _getQueryResults(self, queries: List[GraphQLQuery]) -> List[Any]:
        """
        Execute queries. If a response has zero products AND the variables contain
        a product-level `marketoption`, retry once with that attribute moved to
        `priceFilter.purchaseOption` (and removed from productFilter).
        """

        def _log_gql_errors(payload: Any) -> None:
            try:
                errs = payload.get("errors")
                if errs:
                    logging.error("GraphQL encountered errors:\n%s", json.dumps(errs))
            except Exception:
                pass

        # Try batch first
        try:
            parsed = self._post(queries)
            results: List[Any] = []

            # Batch responses can come back as a list (preferred) or a single dict
            payloads: List[Any]
            if isinstance(parsed, list):
                payloads = parsed
            elif isinstance(parsed, dict):
                payloads = [parsed]
            else:
                payloads = []

            for idx, p in enumerate(payloads):
                if isinstance(p, dict):
                    _log_gql_errors(p)

                try:
                    products = (p or {}).get("data", {}).get("products", [])
                except Exception:
                    products = []

                if (not products) and idx < len(queries) and _has_marketoption(queries[idx].get("variables", {})):
                    try:
                        retry_vars = _pop_marketoption_to_purchaseoption(queries[idx].get("variables", {}))
                        retry_payload = {"query": queries[idx]["query"], "variables": retry_vars}
                        p = self._post(retry_payload)
                        if isinstance(p, dict):
                            _log_gql_errors(p)
                    except Exception as e:
                        logging.debug("Retry with purchaseOption failed: %s", e)

                results.append(_prefer_nonzero_first(p))

            if results:
                return results

        except (URLError, HTTPError) as e:
            logging.debug("Batched GraphQL request failed (%s); falling back to single requests.", e)
        except Exception as e:
            logging.debug("Batched GraphQL parse error (%s); falling back to single requests.", e)

        # Fallback: one-by-one
        results: List[Any] = []
        for q in queries:
            try:
                r = self._post(q)
                if isinstance(r, dict):
                    _log_gql_errors(r)

                products = (r or {}).get("data", {}).get("products", [])
                if (not products) and _has_marketoption(q.get("variables", {})):
                    try:
                        retry_vars = _pop_marketoption_to_purchaseoption(q.get("variables", {}))
                        r = self._post({"query": q["query"], "variables": retry_vars})
                        if isinstance(r, dict):
                            _log_gql_errors(r)
                    except Exception as e:
                        logging.debug("Single retry with purchaseOption failed: %s", e)

                results.append(_prefer_nonzero_first(r))
            except Exception as e:
                logging.error("GraphQL single request failed: %s", e)
                results.append({"data": {"products": []}})
        return results

    def _iter_all_components(self, resource: Any) -> List[tuple[Any, Any]]:
        pairs: List[tuple[Any, Any]] = []

        def comps(r: Any) -> List[Any]:
            if hasattr(r, "price_components") and callable(getattr(r, "price_components")):
                return r.price_components()
            if hasattr(r, "PriceComponents") and callable(getattr(r, "PriceComponents")):
                return r.PriceComponents()
            return getattr(r, "cost_components", []) or []

        def children(r: Any) -> List[Any]:
            if hasattr(r, "sub_resources") and callable(getattr(r, "sub_resources")):
                return r.sub_resources()
            if hasattr(r, "SubResources") and callable(getattr(r, "SubResources")):
                return r.SubResources()
            return getattr(r, "sub_resources", []) or []

        def walk(r: Any) -> None:
            for pc in comps(r):
                pairs.append((r, pc))
            for c in children(r):
                walk(c)

        walk(resource)
        return pairs

    def _batchQueries(self, resource: Any) -> Tuple[List[Tuple[Any, Any]], List[GraphQLQuery]]:
        query_keys: List[Tuple[Any, Any]] = []
        queries: List[GraphQLQuery] = []

        for res, pc in self._iter_all_components(resource):
            pf = _extract_filter(pc, "product_filter", "productFilter")
            prf = _extract_filter(pc, "price_filter", "priceFilter")
            query_keys.append((res, pc))
            queries.append(self._buildQuery(pf, prf))

        return query_keys, queries

    def _unpackQueryResults(
        self,
        query_keys: List[Tuple[Any, Any]],
        query_results: List[Any],
    ) -> Dict[Any, Dict[Any, Any]]:
        out: Dict[Any, Dict[Any, Any]] = {}
        for i, result in enumerate(query_results):
            if i >= len(query_keys):
                break
            r, pc = query_keys[i]
            out.setdefault(r, {})[pc] = result
        return out
