from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Mapping

# These are the schema-style interfaces your resources/components expose
from plancosts.schema.resource import Resource
from plancosts.schema.cost_component import CostComponent


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def _set_component_price(resource: Resource, component: CostComponent, gql_result: Dict[str, Any]) -> None:
    """
    Mirrors Go setCostComponentPrice behavior:
      - If no products/prices -> warn and set 0
      - If multiple products/prices -> warn and use first
      - Set unit price and optional priceHash
    """
    rname = getattr(resource, "name", None) or getattr(resource, "address", None) or "<resource>"
    cname = getattr(component, "name", None) or "<component>"

    data = (gql_result or {}).get("data") or {}
    products = data.get("products") or []
    if not products:
        logging.warning("No products found for %s %s, using 0.00", rname, cname)
        component.SetPrice(Decimal(0))
        return
    if len(products) > 1:
        logging.warning("Multiple products found for %s %s, using the first product", rname, cname)

    prices = products[0].get("prices") or []
    if not prices:
        logging.warning("No prices found for %s %s, using 0.00", rname, cname)
        component.SetPrice(Decimal(0))
        return
    if len(prices) > 1:
        logging.warning("Multiple prices found for %s %s, using the first price", rname, cname)

    first = prices[0]
    price_value = _to_decimal(first.get("USD"))
    price_hash = first.get("priceHash")
    
    # DEBUG: Log what we're setting
    print(f"DEBUG: Setting price for {cname}: USD={price_value}, hash={price_hash}")
    
    component.SetPrice(price_value)

    # Optional traceability like Go's priceHash
    if isinstance(price_hash, str) and price_hash:
        try:
            component.SetPriceHash(price_hash)
            print(f"DEBUG: Successfully set price_hash: {price_hash}")
        except AttributeError as e:
            print(f"DEBUG: Failed to set price_hash: {e}")
    else:
        print(f"DEBUG: No price_hash in GraphQL response for {cname}")


def get_prices(resource: Resource, query_runner) -> None:
    """
    Python equivalent of prices.GetPrices(resource, q QueryRunner).

    query_runner must expose:
      RunQueries(resource) -> Mapping[Resource, Mapping[CostComponent, GraphQLResultDict]]

    This function mutates the cost components in-place by setting their unit prices
    (and optional priceHash) based on the GraphQL results.
    """
    try:
        results_map: Mapping[Any, Mapping[Any, Dict[str, Any]]] = query_runner.RunQueries(resource)
    except Exception as e:
        logging.error("GraphQL query execution failed: %s", e)
        return

    # Iterate results for the top-level resource and any sub-resources included by the runner
    for res_obj, comp_map in (results_map or {}).items():
        for comp_obj, payload in (comp_map or {}).items():
            _set_component_price(res_obj, comp_obj, payload)
