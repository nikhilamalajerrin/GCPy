# plancosts/plancosts/schema/resource_data.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

__all__ = ["JSONResult", "ResourceData"]


# --- Minimal gjson-like result wrapper -----------------

class JSONResult:
    """
    Tiny helper to mimic the gjson.Result API used in code:
      - Exists()
      - String()
      - Float()
      - Int()
      - Bool()
      - Array()
      - Get(path)
      - Value()

    Paths support dot notation and simple [index] for lists, e.g.:
      "root_block_device.volume_size"
      "ebs_block_device[0].iops"
    """

    def __init__(self, value: Any = None) -> None:
        self._v = value

    # Presence
    def Exists(self) -> bool:
        return self._v is not None

    # Converters (best-effort; fall back to zero/empty)
    def String(self) -> str:
        if self._v is None:
            return ""
        try:
            return str(self._v)
        except Exception:
            return ""

    def Float(self) -> float:
        try:
            return float(self._v)
        except Exception:
            return 0.0

    def Int(self) -> int:
        try:
            return int(self._v)
        except Exception:
            return 0

    def Bool(self) -> bool:
        try:
            if isinstance(self._v, bool):
                return self._v
            if isinstance(self._v, (int, float)):
                return self._v != 0
            if isinstance(self._v, str):
                return self._v.strip().lower() in ("1", "true", "yes", "y", "on")
        except Exception:
            pass
        return False

    def Array(self) -> List["JSONResult"]:
        if isinstance(self._v, list):
            return [JSONResult(x) for x in self._v]
        return []

    def Value(self) -> Any:
        return self._v

    # Simple path resolver
    def Get(self, path: str) -> "JSONResult":
        def _parse_segment(seg: str) -> List[Union[str, int]]:
            # Split "key[0]" -> ["key", 0]
            parts: List[Union[str, int]] = []
            buf: List[str] = []
            i = 0
            while i < len(seg):
                c = seg[i]
                if c == "[":
                    # push buffered key if any
                    if buf:
                        parts.append("".join(buf))
                        buf = []
                    # read index
                    j = seg.find("]", i + 1)
                    if j == -1:
                        # malformed; treat as literal
                        buf.append(c)
                        i += 1
                        continue
                    idx_str = seg[i + 1 : j].strip()
                    try:
                        parts.append(int(idx_str))
                    except Exception:
                        # not an int, keep literal
                        parts.append(seg[i : j + 1])
                    i = j + 1
                else:
                    buf.append(c)
                    i += 1
            if buf:
                parts.append("".join(buf))
            return [p for p in parts if p != ""]  # drop empty keys

        cur: Any = self._v
        if not path:
            return JSONResult(cur)

        for raw_seg in path.split("."):
            for seg in _parse_segment(raw_seg):
                if isinstance(seg, int):
                    if isinstance(cur, list) and 0 <= seg < len(cur):
                        cur = cur[seg]
                    else:
                        return JSONResult(None)
                else:
                    if isinstance(cur, dict) and seg in cur:
                        cur = cur[seg]
                    else:
                        return JSONResult(None)
        return JSONResult(cur)


# --- ResourceData (schema mirror) ------------------

@dataclass
class ResourceData:
    """
    Python pkg/schema/resource_data, extended with ProviderName.

      type ResourceData struct {
          Type          string
          ProviderName  string
          Address       string
          rawValues     gjson.Result
          referencesMap map[string][]*ResourceData
      }

    Back-compat notes:
    - Supports both constructor forms:
        NewResourceData(type, address, raw_values)
        NewResourceData(type, provider_name, address, raw_values)
    - Public attributes use capitalization (Type, Address, ProviderName).
    """

    Type: str
    Address: str
    _raw_values: Dict[str, Any] = field(default_factory=dict)
    _references_map: Dict[str, List["ResourceData"]] = field(default_factory=dict)
    ProviderName: str = ""  # matches; kept last for dataclass defaults

    @classmethod
    def NewResourceData(
        cls,
        resource_type: str,
        address_or_provider: str,
        raw_or_address: Any,
        raw_values_or_provider: Any = None,
    ) -> "ResourceData":
        """
        Back-compat constructor supporting both signatures:

          1) Legacy (3-arg):
             NewResourceData(type, address, raw_values)

          2) New (4-arg with provider):
             NewResourceData(type, provider_name, address, raw_values)
        """
        # 4-arg form: (type, provider_name, address, raw_values)
        if raw_values_or_provider is not None:
            provider_name = address_or_provider or ""
            address = str(raw_or_address or "")
            raw_values = raw_values_or_provider if isinstance(raw_values_or_provider, dict) else {}
            # each instance gets its own maps
            return cls(resource_type, address, dict(raw_values), {}, provider_name)

        # 3-arg form: (type, address, raw_values)
        address = str(address_or_provider or "")
        raw_values = raw_or_address if isinstance(raw_or_address, dict) else {}
        return cls(resource_type, address, dict(raw_values), {}, "")

    # API
    def Get(self, key: str) -> JSONResult:
        return JSONResult(self._raw_values).Get(key)

    def References(self, key: str) -> List["ResourceData"]:
        return self._references_map.get(key, [])

    def AddReference(self, key: str, reference: "ResourceData") -> None:
        self._references_map.setdefault(key, []).append(reference)

    # Python-friendly helpers
    def raw_values(self) -> Dict[str, Any]:
        return self._raw_values

    def references_map(self) -> Dict[str, List["ResourceData"]]:
        return self._references_map
