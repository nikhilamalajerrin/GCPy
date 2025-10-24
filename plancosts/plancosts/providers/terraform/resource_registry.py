# plancosts/providers/terraform/resource_registry.py
from __future__ import annotations
from typing import Callable, Dict
from threading import Lock

from plancosts.providers.terraform.aws.resource_registry import ResourceRegistry as AWS_RESOURCE_REGISTRY

# Thread-safe singleton pattern like Go's sync.Once
_resource_registry: Dict[str, Callable] | None = None
_lock = Lock()


def _init_registry() -> Dict[str, Callable]:
    """
    Initialize and merge all provider registries.
    Currently only AWS is supported.
    """
    registry: Dict[str, Callable] = {}
    # Merge AWS resources
    registry.update(AWS_RESOURCE_REGISTRY)
    return registry


def get_resource_registry() -> Dict[str, Callable]:
    """
    Python equivalent of getResourceRegistry() in Go.

    Lazily initializes the global resource registry once,
    merges provider registries (AWS, GCP, etc.),
    and returns the cached mapping.
    """
    global _resource_registry
    if _resource_registry is None:
        with _lock:
            if _resource_registry is None:
                _resource_registry = _init_registry()
    return dict(_resource_registry)
