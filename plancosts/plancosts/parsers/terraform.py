"""
Terraform plan parser for extracting resources.
"""
import json
from typing import List, Dict, Any
from plancosts.base.resource import BaseResource, Resource
from plancosts.base.filters import Filter
from plancosts.providers.aws import provider as aws_provider
from plancosts.providers.aws import ec2 as aws_ec2


def get_provider_filters(provider: str, region: str) -> List[Filter]:
    """
    Get provider-specific filters based on provider and region.
    """
    if provider == "aws":
        return aws_provider.get_default_filters(region)
    return []


def get_resource_mapping(resource_type: str):
    """
    Get resource mapping for a specific Terraform resource type.
    """
    if resource_type == "aws_instance":
        return aws_ec2.Ec2Instance  # match Go's symbol name
    return None


def parse_plan_file(file_path: str) -> List[Resource]:
    """
    Parse a Terraform plan JSON file and extract resources.
    """
    with open(file_path, "r") as f:
        plan_data = json.load(f)

    # Extract region from provider config
    terraform_region = (
        plan_data.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )

    provider_filters = get_provider_filters("aws", terraform_region)

    # Extract resources from planned values
    resource_map: Dict[str, Resource] = {}
    terraform_resources = (
        plan_data.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    for tr in terraform_resources:
        address = tr.get("address", "")
        resource_type = tr.get("type", "")
        raw_values = tr.get("values") or {}  # ensure dict
        resource_mapping = get_resource_mapping(resource_type)
        if resource_mapping:
            resource_map[address] = BaseResource(
                address=address,
                raw_values=raw_values,
                resource_mapping=resource_mapping,
                provider_filters=provider_filters,
            )

    # Index config resources by address for quick lookup
    cfg_resources = (
        plan_data.get("configuration", {}).get("root_module", {}).get("resources", [])
    )
    cfg_index = {r.get("address"): r for r in cfg_resources}

    # Add references
    for resource in resource_map.values():
        cfg = cfg_index.get(resource.address())
        if cfg:
            _add_references(resource, cfg, resource_map)

    return list(resource_map.values())


def _add_references(
    resource: Resource, resource_config: Dict[str, Any], resource_map: Dict[str, Resource]
) -> None:
    """
    Add references between resources based on configuration.
    """
    expressions = resource_config.get("expressions", {})
    for _, value in expressions.items():
        ref_addr = None

        # Direct references
        if isinstance(value, dict) and "references" in value:
            refs = value.get("references") or []
            if refs:
                ref_addr = refs[0]

        # References in arrays
        elif isinstance(value, list) and value:
            first_item = value[0]
            if isinstance(first_item, dict):
                id_val = first_item.get("id")
                if isinstance(id_val, dict):
                    refs = id_val.get("references") or []
                    if refs:
                        ref_addr = refs[0]

        # Add reference if found
        if ref_addr and ref_addr in resource_map:
            resource.add_reference(ref_addr, resource_map[ref_addr])
