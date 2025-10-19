from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

# var defaultVolumeSize = 8
DEFAULT_VOLUME_SIZE: int = 8

def strptr(s: Optional[str]) -> Optional[str]:
    """
    In Python we just return the string (or None) directly.
    """
    return s

def d(val: Union[str, int, float, Decimal]) -> Decimal:
    """
    Convenience: normalize numbers to Decimal, similar to shopspring/decimal.
    """
    return val if isinstance(val, Decimal) else Decimal(str(val))
