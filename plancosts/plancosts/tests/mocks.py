from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


# =========================
# Helpers for fake GraphQL
# =========================

def _graph_ql_result_for_price(price: Decimal) -> Dict[str, Any]:
    """
    Shape that the code under test expects:
      data.products[0].prices[0].USD
    """
    s = f"{Decimal(price):f}"  # normalize to a simple decimal string
    return {
        "data": {
            "products": [
                {
                    "prices": [
                        {"USD": s}
                    ]
                }
            ]
        }
    }


def _flatten_subresources(r: "TestResource") -> List["TestResource"]:
    out: List[TestResource] = []
    stack = list(r.sub_resources())
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(cur.sub_resources())
    return out


# =========================
# Price component test double
# =========================

class TestPriceComponent:
    """
    Minimal test double that mirrors what tests need:
      - name()
      - filters()
      - set_price(), price (property)
      - hourly_cost() (pre-set value for assertions)
    """
    def __init__(self, name: str, hourly_cost: Decimal, filters: Optional[List[Dict[str, Any]]] = None):
        self._name = name
        self._filters = list(filters or [])
        self._price: Decimal = Decimal("0")
        self._hourly_cost: Decimal = Decimal(hourly_cost)

    # Interface used by the app/tests
    def name(self) -> str:
        return self._name

    def filters(self) -> List[Dict[str, Any]]:
        return list(self._filters)

    def set_price(self, price: Decimal) -> None:
        self._price = Decimal(price)

    def hourly_cost(self) -> Decimal:
        return self._hourly_cost

    # Property so tests can do `pc.price`
    @property
    def price(self) -> Decimal:
        return self._price


# Back-compat class expected by tests.
# Important: tests call as PC(Decimal("0.1"), name="…"), so accept hourly_cost first.
class PriceComponentMock(TestPriceComponent):
    def __init__(self, hourly_cost: Decimal, name: str = "pc", filters: Optional[List[Dict[str, Any]]] = None):
        super().__init__(name=name, hourly_cost=Decimal(hourly_cost), filters=filters)


# =========================
# Resource test double
# =========================

class TestResource:
    """
    Minimal resource double:
      - address()
      - sub_resources(), add_sub_resource()
      - price_components(), add_price_component()
      - references(), add_reference()
      - has_cost()
    """
    def __init__(
        self,
        address: str,
        *,
        # Support both new (pcs/subs) and old (price_components/sub_resources) names
        pcs: Optional[List[TestPriceComponent]] = None,
        subs: Optional[List["TestResource"]] = None,
        price_components: Optional[List[TestPriceComponent]] = None,
        sub_resources: Optional[List["TestResource"]] = None,
    ):
        self._address = address
        pcs = pcs if pcs is not None else price_components
        subs = subs if subs is not None else sub_resources
        self._pcs = list(pcs or [])
        self._subs = list(subs or [])
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

    # Convenience for building trees in tests
    def add_price_component(self, pc: TestPriceComponent) -> None:
        self._pcs.append(pc)

    def add_sub_resource(self, r: "TestResource") -> None:
        self._subs.append(r)


# Back-compat alias expected by some tests
class ResourceMock(TestResource):
    pass


# =========================
# Query runner test double
# =========================

class TestQueryRunner:
    """
    Fake GraphQL runner.

    Usage:
      q = TestQueryRunner()
      q.set_override(resource, pc, Decimal("0.123"))
      results_map = q.run_queries(resource)

    Returns a mapping:
      { resource_or_subresource: { price_component: graphql_result_dict } }
    where graphql_result_dict has the new `prices[].USD` shape.
    """
    def __init__(self) -> None:
        self.overrides: Dict[Tuple[TestResource, TestPriceComponent], Decimal] = {}

    def set_override(self, resource: TestResource, pc: TestPriceComponent, price: Decimal) -> None:
        self.overrides[(resource, pc)] = Decimal(price)

    def _get_price(self, resource: TestResource, pc: TestPriceComponent) -> Decimal:
        return self.overrides.get((resource, pc), Decimal("0.1"))

    def run_queries(self, resource: TestResource) -> Dict[TestResource, Dict[TestPriceComponent, Dict[str, Any]]]:
        results: Dict[TestResource, Dict[TestPriceComponent, Dict[str, Any]]] = {}

        # Top-level price components
        for pc in resource.price_components():
            results.setdefault(resource, {})[pc] = _graph_ql_result_for_price(self._get_price(resource, pc))

        # All descendants (flattened), same behavior as production code
        for sub in _flatten_subresources(resource):
            for pc in sub.price_components():
                results.setdefault(sub, {})[pc] = _graph_ql_result_for_price(self._get_price(sub, pc))

        return results


__all__ = [
    "TestPriceComponent",
    "PriceComponentMock",   # legacy name expected by some tests
    "TestResource",
    "ResourceMock",         # legacy name expected by some tests
    "TestQueryRunner",
]
