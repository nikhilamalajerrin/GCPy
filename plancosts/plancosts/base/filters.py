"""
Filter & value-mapping helpers (refactored model).
"""
from __future__ import annotations
from typing import List, Optional, Callable, Any, Dict


class Filter:
    def __init__(self, key: str, value: str, operation: Optional[str] = None):
        self.key = key
        self.value = value
        self.operation = operation

    def as_tuple(self):
        return (self.key, self.operation)


class ValueMapping:
    def __init__(self, from_key: str, to_key: str, to_value_fn: Optional[Callable[[Any], str]] = None):
        self.from_key = from_key
        self.to_key = to_key
        self.to_value_fn = to_value_fn

    def mapped_value(self, from_val: Any) -> str:
        if self.to_value_fn:
            return self.to_value_fn(from_val)
        return "" if from_val is None else f"{from_val}"


def merge_filters(*filter_sets: List[Filter]) -> List[Filter]:
    merged: Dict[tuple, Filter] = {}
    for fs in filter_sets:
        for f in fs or []:
            merged[f.as_tuple()] = f
    return list(merged.values())


def map_filters(value_mappings: List[ValueMapping], values: Dict[str, Any]) -> List[Filter]:
    out: List[Filter] = []
    for vm in value_mappings or []:
        if vm.from_key in values:
            to_val = vm.mapped_value(values[vm.from_key])
            if to_val:
                out.append(Filter(key=vm.to_key, value=to_val))
    return out
