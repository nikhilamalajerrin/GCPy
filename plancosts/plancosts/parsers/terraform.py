"""
Terraform plan parser for extracting resources.
"""
from __future__ import annotations

import json
from typing import List, Dict, Any
from plancosts.base.resource import BaseResource, Resource
from plancosts.base.filters import Filter
from plancosts.providers.aws import provider as aws_provider


def get_provider_filters(provider: str, region: str) -> List[Filter]:
    if provider == "aws":
        return aws_provider.get_default_filters(region)
    return []


def get_resource_mapping(resource_type: str, raw_values: Dict[str, Any]):
    # AWS
    if resource_type == "aws_instance":
        from plancosts.providers.aws import ec2 as aws_ec2
        return aws_ec2.Ec2Instance
    if resource_type == "aws_ebs_volume":
        from plancosts.providers.aws import ebs as aws_ebs
        return aws_ebs.EbsVolume
    if resource_type == "aws_ebs_snapshot":
        from plancosts.providers.aws import ebs as aws_ebs
        return aws_ebs.EbsSnapshot
    if resource_type == "aws_ebs_snapshot_copy":
        from plancosts.providers.aws import ebs as aws_ebs
        return aws_ebs.EbsSnapshotCopy
    if resource_type == "aws_autoscaling_group":
        # choose mapping based on whether launch_template is present
        lt = raw_values.get("launch_template")
        if isinstance(lt, list) and len(lt) > 0:
            from plancosts.providers.aws import ec2_autoscaling as asg
            return asg.AutoscalingGroupLaunchTemplate
        from plancosts.providers.aws import ec2_autoscaling as asg
        return asg.AutoscalingGroupLaunchConfiguration

    # default: non-costable resource mapping
    return aws_provider.DefaultResourceMapping


def parse_plan_file(file_path: str) -> List[Resource]:
    with open(file_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    terraform_region = (
        plan_data.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )
    provider_filters = get_provider_filters("aws", terraform_region)

    resource_map: Dict[str, Resource] = {}
    terraform_resources = (
        plan_data.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )
    for tr in terraform_resources:
        address = tr.get("address", "")
        resource_type = tr.get("type", "")
        raw_values = tr.get("values") or {}
        mapping = get_resource_mapping(resource_type, raw_values)
        if mapping:
            resource_map[address] = BaseResource(
                address=address,
                raw_values=raw_values,
                resource_mapping=mapping,
                provider_filters=provider_filters,
            )

    cfg_resources = plan_data.get("configuration", {}).get("root_module", {}).get("resources", [])
    cfg_index = {r.get("address"): r for r in cfg_resources if r.get("address")}

    for resource in resource_map.values():
        cfg = cfg_index.get(resource.address())
        if cfg:
            _add_references(resource, cfg, resource_map)
        # NEW: now that references are wired, build subresources (may depend on overrides)
        resource.add_sub_resources()

    return list(resource_map.values())


def _add_references(resource: Resource, resource_config: Dict[str, Any], resource_map: Dict[str, Resource]) -> None:
    expressions = resource_config.get("expressions", {})
    if not isinstance(expressions, dict):
        return
    for key, value in expressions.items():
        ref_addr = None
        if isinstance(value, dict) and "references" in value:
            refs = value.get("references") or []
            if refs:
                ref_addr = refs[0]
        elif isinstance(value, list) and value:
            first_item = value[0]
            if isinstance(first_item, dict):
                id_val = first_item.get("id")
                if isinstance(id_val, dict):
                    refs = id_val.get("references") or []
                    if refs:
                        ref_addr = refs[0]
        if ref_addr and ref_addr in resource_map:
            resource.add_reference(str(key), resource_map[ref_addr])
