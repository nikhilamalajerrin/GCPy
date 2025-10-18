from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

# Mirrors Go: var defaultVolumeSize = 8
DEFAULT_VOLUME_SIZE: int = 8

def strptr(s: Optional[str]) -> Optional[str]:
    """
    Go's *string helper is used to pass nil-or-string.
    In Python we just return the string (or None) directly.
    """
    return s

def d(val: Union[str, int, float, Decimal]) -> Decimal:
    """
    Convenience: normalize numbers to Decimal, similar to shopspring/decimal usage in Go.
    """
    return val if isinstance(val, Decimal) else Decimal(str(val))
