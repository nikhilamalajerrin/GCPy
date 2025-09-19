# plancosts/base/filters.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Filter:
    key: str
    value: str
    operation: str = "=="


@dataclass(frozen=True)
class ValueMapping:
    from_key: str
    to_key: str
    map_func: Optional[Callable[[Any], str]] = None

    def mapped_value(self, from_val: Any) -> str:
        return self.map_func(from_val) if self.map_func else str(from_val)

    # Back-compat for any CamelCase calls
    def MappedValue(self, from_val: Any) -> str:  # noqa: N802
        return self.mapped_value(from_val)


def merge_filters(*lists: Iterable[Filter]) -> List[Filter]:
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
    out: List[Filter] = []
    for vm in value_mappings:
        if vm.from_key in values:
            out.append(
                Filter(
                    key=vm.to_key,
                    value=vm.mapped_value(values[vm.from_key]),
                    operation="==",  # <- fixed
                )
            )
    return out
