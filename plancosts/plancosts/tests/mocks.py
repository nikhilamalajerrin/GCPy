from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


# ---- Test doubles ----

class TestPriceComponent:
    """
    Mirrors the Go testPriceComponent (post-commit):
    - name
    - filters
    - SetPrice/Price
    - HourlyCost (fixed value for tests)
    """
    def __init__(self, name: str, hourly_cost: Decimal, filters: Optional[List[Dict[str, Any]]] = None):
        self._name = name
        self._filters = list(filters or [])
        self._price: Decimal = Decimal("0")
        self._hourly_cost: Decimal = Decimal(hourly_cost)

    def name(self) -> str:
        return self._name

    def filters(self) -> List[Dict[str, Any]]:
        return list(self._filters)

    # Matches Go: SetPrice + HourlyCost + Price()
    def set_price(self, price: Decimal) -> None:
        self._price = Decimal(price)

    def hourly_cost(self) -> Decimal:
        return self._hourly_cost

    def price(self) -> Decimal:
        return self._price


class TestResource:
    """
    Mirrors the Go testResource:
    - address
    - sub_resources
    - price_components
    - references (map[string]Resource)
    - has_cost() -> True
    """
    def __init__(
        self,
        address: str,
        price_components: Optional[List[TestPriceComponent]] = None,
        sub_resources: Optional[List["TestResource"]] = None,
    ):
        self._address = address
        self._pcs = list(price_components or [])
        self._subs = list(sub_resources or [])
        self._refs: Dict[str, "TestResource"] = {}

    def address(self) -> str:
        return self._address

    def sub_resources(self) -> List["TestResource"]:
        return self._subs

    def price_components(self) -> List[TestPriceComponent]:
        return self._pcs

    def references(self) -> Dict[str, "TestResource"]:
        return self._refs

    def add_reference(self, name: str, resource: "TestResource") -> None:
        self._refs[name] = resource

    def has_cost(self) -> bool:
        return True

    # For convenience in tests
    def add_price_component(self, pc: TestPriceComponent) -> None:
        self._pcs.append(pc)

    def add_sub_resource(self, r: "TestResource") -> None:
        self._subs.append(r)


# ---- Fake GraphQL layer (mirrors mocks.go behavior) ----

def _graph_ql_result_for_price(price: Decimal) -> Dict[str, Any]:
    """
    Generates the same JSON shape the Go tests expect:
    data.products[0].onDemandPricing[0].priceDimensions[0].pricePerUnit.USD
    """
    return {
        "data": {
            "products": [
                {
                    "onDemandPricing": [
                        {
                            "priceDimensions": [
                                {"unit": "Hrs", "pricePerUnit": {"USD": f"{Decimal(price):f}"}}
                            ]
                        }
                    ]
                }
            ]
        }
    }


class TestQueryRunner:
    """
    Simple price source with optional overrides:
      overrides[(resource, price_component)] = price
    run_queries(resource) returns the result map for top-level and immediate sub-resources,
    mirroring the Go mock’s batching.
    """
    def __init__(self) -> None:
        self.overrides: Dict[Tuple[TestResource, TestPriceComponent], Decimal] = {}

    def set_override(self, resource: TestResource, pc: TestPriceComponent, price: Decimal) -> None:
        self.overrides[(resource, pc)] = Decimal(price)

    def _get_price(self, resource: TestResource, pc: TestPriceComponent) -> Decimal:
        return self.overrides.get((resource, pc), Decimal("0.1"))

    def run_queries(self, resource: TestResource) -> Dict[TestResource, Dict[TestPriceComponent, Dict[str, Any]]]:
        results: Dict[TestResource, Dict[TestPriceComponent, Dict[str, Any]]] = {}

        # Top-level PCs
        for pc in resource.price_components():
            results.setdefault(resource, {})[pc] = _graph_ql_result_for_price(self._get_price(resource, pc))

        # Immediate sub-resources (commit batches only one level)
        for sub in resource.sub_resources():
            for pc in sub.price_components():
                results.setdefault(resource, {})[pc] = _graph_ql_result_for_price(self._get_price(resource, pc))

        return results
