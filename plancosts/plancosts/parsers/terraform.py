"""
Terraform plan parser for extracting resources.
"""
import json
from typing import List, Dict, Any, Optional
from plancosts.base.resource import BaseResource, Resource
from plancosts.base.filters import Filter
from plancosts.providers.aws import provider as aws_provider
from plancosts.providers.aws import ec2 as aws_ec2


def get_provider_filters(provider: str, region: str) -> List[Filter]:
    """
    Get provider-specific filters based on provider and region.
    
    Args:
        provider: Cloud provider name (e.g., 'aws')
        region: Region code
    
    Returns:
        List of filters for the provider
    """
    if provider == "aws":
        return aws_provider.get_default_filters(region)
    
    return []


def get_resource_mapping(resource_type: str):
    """
    Get resource mapping for a specific Terraform resource type.
    
    Args:
        resource_type: Terraform resource type (e.g., 'aws_instance')
    
    Returns:
        ResourceMapping or None if not supported
    """
    if resource_type == "aws_instance":
        return aws_ec2.ec2_instance
    
    return None


def parse_plan_file(file_path: str) -> List[Resource]:
    """
    Parse a Terraform plan JSON file and extract resources.
    
    Args:
        file_path: Path to the Terraform plan JSON file
    
    Returns:
        List of Resource objects
    
    Raises:
        FileNotFoundError: If plan file doesn't exist
        json.JSONDecodeError: If plan file is not valid JSON
    """
    # Read and parse the plan file
    with open(file_path, 'r') as f:
        plan_data = json.load(f)
    
    # Extract region from provider config
    terraform_region = (plan_data.get("configuration", {})
                               .get("provider_config", {})
                               .get("aws", {})
                               .get("expressions", {})
                               .get("region", {})
                               .get("constant_value", ""))
    
    provider_filters = get_provider_filters("aws", terraform_region)
    
    # Extract resources from planned values
    resource_map = {}
    terraform_resources = (plan_data.get("planned_values", {})
                                    .get("root_module", {})
                                    .get("resources", []))
    
    for terraform_resource in terraform_resources:
        address = terraform_resource.get("address", "")
        resource_type = terraform_resource.get("type", "")
        raw_values = terraform_resource.get("values", {})
        
        resource_mapping = get_resource_mapping(resource_type)
        if resource_mapping:
            resource = BaseResource(
                address=address,
                raw_values=raw_values,
                resource_mapping=resource_mapping,
                provider_filters=provider_filters
            )
            resource_map[address] = resource
    
    # Add references between resources
    for resource in resource_map.values():
        # Find resource configuration
        config_resources = (plan_data.get("configuration", {})
                                    .get("root_module", {})
                                    .get("resources", []))
        
        for config_resource in config_resources:
            if config_resource.get("address") == resource.address():
                _add_references(resource, config_resource, resource_map)
    
    return list(resource_map.values())


def _add_references(resource: Resource, 
                    resource_config: Dict[str, Any], 
                    resource_map: Dict[str, Resource]):
    """
    Add references between resources based on configuration.
    
    Args:
        resource: The resource to add references to
        resource_config: The resource's configuration
        resource_map: Map of all resources by address
    """
    expressions = resource_config.get("expressions", {})
    
    for key, value in expressions.items():
        ref_addr = None
        
        # Check for direct references
        if isinstance(value, dict) and "references" in value:
            refs = value.get("references", [])
            if refs and len(refs) > 0:
                ref_addr = refs[0]
        
        # Check for references in arrays
        elif isinstance(value, list) and len(value) > 0:
            first_item = value[0]
            if isinstance(first_item, dict) and "id" in first_item:
                id_val = first_item["id"]
                if isinstance(id_val, dict) and "references" in id_val:
                    refs = id_val.get("references", [])
                    if refs and len(refs) > 0:
                        ref_addr = refs[0]
        
        # Add reference if found
        if ref_addr and ref_addr in resource_map:
            resource.add_reference(ref_addr, resource_map[ref_addr])