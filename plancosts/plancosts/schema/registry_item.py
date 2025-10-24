from __future__ import annotations
from typing import Callable, List, Optional

class RegistryItem:
    """
    Represents a registry entry for a Terraform resource type.

    Attributes:
        name: Canonical resource type name, e.g. "aws_instance".
        notes: Docstring-style notes for generated documentation.
        rfunc: Callable that constructs the resource (resource_data -> Resource).
    """
    def __init__(
        self,
        name: str,
        rfunc: Callable,
        notes: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.notes = notes or []
        self.rfunc = rfunc

    def __repr__(self) -> str:
        return f"RegistryItem(name={self.name!r}, notes={self.notes})"
