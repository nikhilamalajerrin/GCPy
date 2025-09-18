# plancosts/base/filters.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

# -----------------
# Data structures
# -----------------

@dataclass(frozen=True)
class Filter:
    key: str
    value: str

@dataclass(frozen=True)
class ValueMapping:
    from_key: str
    to_key: str
    map_func: Optional[Callable[[Any], str]] = None  # <— tests expect this name

    def mapped_value(self, from_val: Any) -> str:
        return self.map_func(from_val) if self.map_func else str(from_val)

# -----------------
# Helpers
# -----------------

def merge_filters(*lists: Iterable[Filter]) -> List[Filter]:
    """
    Merge multiple lists of Filter. Later lists override earlier ones by key.
    Order is stable by first appearance of a key.
    """
    order: List[str] = []
    latest: Dict[str, str] = {}

    for lst in lists:
        for f in lst:
            if f.key not in latest:
                order.append(f.key)
            latest[f.key] = f.value  # override with latest value

    return [Filter(key=k, value=latest[k]) for k in order]

def map_filters(value_mappings: Iterable[ValueMapping], values: Dict[str, Any]) -> List[Filter]:
    """
    Build Filter list from a dict of values according to given mappings.
    Missing keys are skipped. If map_func is provided it is applied.
    """
    out: List[Filter] = []
    for vm in value_mappings:
        if vm.from_key in values:
            out.append(Filter(key=vm.to_key, value=vm.mapped_value(values[vm.from_key])))
    return out
