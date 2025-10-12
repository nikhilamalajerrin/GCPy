from __future__ import annotations

import re
from typing import List

# Matches module.<name> (no index)
_MODULE_RE = re.compile(r"module\.([^\[]*)")
_ARRAY_IDX_RE = re.compile(r"\[\d+\]")

def address_resource_part(address: str) -> str:
    parts = address.split(".")
    resource_parts = parts[-2:]
    return ".".join(resource_parts)

def address_module_part(address: str) -> str:
    parts = address.split(".")
    module_parts = parts[:-2]
    return ".".join(module_parts)

def address_module_names(address: str) -> List[str]:
    matches = _MODULE_RE.findall(address_module_part(address))
    return matches or []

def strip_address_array(address: str) -> str:
    """
    Remove [N] array suffixes from the *resource* part, e.g.
    "aws_x.y[0]" -> "aws_x.y"
    (We keep module path intact; TF config addresses often omit [N])
    """
    return _ARRAY_IDX_RE.sub("", address)

def qualify(module_addr: str, ref_addr: str) -> str:
    """Prefix a ref address with the current module path if present."""
    return f"{module_addr}.{ref_addr}" if module_addr else ref_addr

def parse_module_name(module_addr: str) -> str:
    m = _MODULE_RE.search(module_addr)
    return m.group(1) if m else ""
