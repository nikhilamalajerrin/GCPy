from __future__ import annotations

def parse_module_name(module_addr: str) -> str:
    # "module.child" or "module.child[0]" -> "child"
    if not module_addr.startswith("module."):
        return ""
    tail = module_addr.split(".", 1)[1]
    return tail.split("[", 1)[0]

def strip_address_array(address: str) -> str:
    # "aws_thing.example[0]" -> "aws_thing.example"
    return address.split("[", 1)[0]

def qualify(module_addr: str, ref_addr: str) -> str:
    if not module_addr:
        return ref_addr
    return f"{module_addr}.{ref_addr}"
