# plancosts/providers/terraform/resource_registry.py
from __future__ import annotations

from .aws.resource_registry import ResourceRegistry as AWS_RESOURCE_REGISTRY

# If we later add other cloud providers, merge them here too.
_RESOURCE_REGISTRY: dict[str, callable] = {}
_RESOURCE_REGISTRY.update(AWS_RESOURCE_REGISTRY)


def get_resource_registry() -> dict[str, callable]:
    # Return a copy so callers don’t mutate the module registry by accident
    return dict(_RESOURCE_REGISTRY)
