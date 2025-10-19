# plancosts/base/filters.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Filter:
    key: str
    value: str
    operation: str = ""


@dataclass(frozen=True)
class ValueMapping:
    from_key: str
    to_key: str
    map_func: Optional[Callable[[Any], str]] = None

    def mapped_value(self, from_val: Any) -> str:
        if self.map_func is not None:
            v = self.map_func(from_val)
            return "" if v is None else str(v)

        if from_val is None:
            return ""
        return str(from_val)

    def MappedValue(self, from_val: Any) -> str:  # noqa: N802
        return self.mapped_value(from_val)


def merge_filters(*lists: Iterable[Filter]) -> List[Filter]:
    """
    key with 'last write wins'. Keep stable order of first sighting.
    """
    order: List[str] = []
    latest: Dict[str, Filter] = {}
    for lst in lists:
        for f in lst:
            if f.key not in latest:
                order.append(f.key)
            latest[f.key] = f
    return [latest[k] for k in order]


def map_filters(
    value_mappings: Iterable[ValueMapping], values: Dict[str, Any]
) -> List[Filter]:
    """
    MapFilters iterates value map -> mappings and only adds when mapped value != "".
    """
    out: List[Filter] = []

    for vm in value_mappings:
        if vm.from_key in values:
            to_val = vm.mapped_value(values[vm.from_key])
            if to_val != "":
                out.append(Filter(key=vm.to_key, value=to_val))
    return out
