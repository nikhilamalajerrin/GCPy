# plancosts/schema/registry_item.py
from __future__ import annotations
from typing import Callable, List, Optional

class RegistryItem:
    """
    Represents a registry entry for a Terraform resource type.

    Attributes:
        name: Canonical resource type name, e.g. "aws_instance".
        aliases: Alternative names that map to the same handler.
        notes: Docstring-style notes for generated documentation.
        rfunc: Callable that constructs the resource (resource_data -> Resource).
    """
    def __init__(
        self,
        name: str,
        rfunc: Callable,
        aliases: Optional[List[str]] = None,
        notes: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.aliases = aliases or []
        self.notes = notes or []
        self.rfunc = rfunc

    def __repr__(self) -> str:
        return f"RegistryItem(name={self.name!r}, aliases={self.aliases}, notes={self.notes})"
