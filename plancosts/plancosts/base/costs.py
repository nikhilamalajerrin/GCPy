# plancosts/base/costs.py
from __future__ import annotations

from typing import Any, List

# Use the new prices pipeline
from plancosts.prices.prices import get_prices


def get_cost_breakdowns(runner: Any, resources: List[Any]):
    """
    Parity wrapper: price each resource via the prices layer and
    return the list. The table renderer should accept priced resources.
    """
    for r in resources:
        # Price the resource directly or via its schema representation
        to_schema = getattr(r, "to_schema", None)
        target = to_schema() if callable(to_schema) else r
        # Mutates in-place by setting unit prices & price hashes
        get_prices(target, runner)
    return resources  # Return original resources, now priced