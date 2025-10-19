# tests/unit/aws/test_ecs_service_internal.py
from __future__ import annotations

from decimal import Decimal
import pytest

# Prefer the canonical package path:
try:
    from plancosts.providers.terraform.aws.ecs_service import (
        _convert_resource_string as convertResourceString,
    )
except Exception:
    # Fallback for older layouts during the port
    from plancosts.plancosts.providers.terraform.aws.ecs_service import (  # type: ignore
        _convert_resource_string as convertResourceString,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "input_str, expected",
    [
        ("1GB", Decimal("1")),
        ("1gb", Decimal("1")),
        (" 1 Gb ", Decimal("1")),   # mixed case + surrounding whitespace
        ("0.5 GB", Decimal("0.5")),
        (".5 GB", Decimal("0.5")),
        ("1VCPU", Decimal("1")),
        ("1vcpu", Decimal("1")),
        (" 1 vCPU ", Decimal("1")), # mixed case + surrounding whitespace
        ("1024", Decimal("1")),     # MiB → GiB
        (" 1024 ", Decimal("1")),
        ("512", Decimal("0.5")),
        ("2048", Decimal("2")),
    ],
)
def test_convert_resource_string(input_str: str, expected: Decimal) -> None:
    actual = convertResourceString(input_str)
    assert actual == expected, f"Conversion of {input_str!r} failed, got {actual}, expected {expected}"
