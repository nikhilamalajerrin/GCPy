# tests/test_filters.py
import pytest
from plancosts.base.filters import Filter, ValueMapping, merge_filters, map_filters

def test_mapped_value_passthrough():
    vm = ValueMapping(from_key="from", to_key="to")
    assert vm.mapped_value("val") == "val"

def test_mapped_value_with_func():
    vm = ValueMapping(from_key="from", to_key="to",
                      map_func=lambda v: f"{v}.mapped")
    assert vm.mapped_value("val") == "val.mapped"

def test_merge_filters_overrides_by_key():
    a = [Filter(key="key1", value="val1"), Filter(key="key2", value="val2")]
    b = [Filter(key="key3", value="val3"), Filter(key="key1", value="val1-updated")]
    result = merge_filters(a, b)
    # order should be stable: key1 (updated), key2, key3
    assert result == [
        Filter(key="key1", value="val1-updated"),
        Filter(key="key2", value="val2"),
        Filter(key="key3", value="val3"),
    ]

def test_map_filters_builds_expected_filters():
    mappings = [
        ValueMapping("fromKey1", "toKey1"),
        ValueMapping("fromKey2", "toKey2", map_func=lambda v: f"{v}.mapped"),
    ]
    values = {"fromKey1": 1, "fromKey2": "val2", "fromKey3": "ignored"}
    result = map_filters(mappings, values)
    assert result == [
        Filter(key="toKey1", value="1"),
        Filter(key="toKey2", value="val2.mapped"),
    ]
