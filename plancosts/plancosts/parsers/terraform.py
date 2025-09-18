"""
Terraform plan parser that builds typed AWS Terraform resources.

This version constructs resources from plancosts.providers.aws_terraform.*
and wires up references between them (e.g. ASG -> Launch Template).
"""
from __future__ import annotations

import json
from typing import Dict, Any, List, Optional

from plancosts.base.resource import Resource  # type: ignore

# Typed AWS Terraform resources
from plancosts.providers.aws_terraform.ebs_volume import EbsVolume
from plancosts.providers.aws_terraform.ebs_snapshot import EbsSnapshot
from plancosts.providers.aws_terraform.ebs_snapshot_copy import EbsSnapshotCopy
from plancosts.providers.aws_terraform.ec2_instance import Ec2Instance
from plancosts.providers.aws_terraform.ec2_launch_configuration import Ec2LaunchConfiguration
from plancosts.providers.aws_terraform.ec2_launch_template import Ec2LaunchTemplate
from plancosts.providers.aws_terraform.ec2_autoscaling_group import Ec2AutoscalingGroup


def _aws_region(plan_data: Dict[str, Any]) -> str:
    return (
        plan_data.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )


def _create_resource(
    rtype: str,
    address: str,
    raw_values: Dict[str, Any],
    aws_region: str,
) -> Optional[Resource]:
    """
    Factory: create the correct typed resource for the given terraform resource type.
    Unknown types return None (ignored).
    """
    if rtype == "aws_instance":
        return Ec2Instance(address, aws_region, raw_values)
    if rtype == "aws_ebs_volume":
        return EbsVolume(address, aws_region, raw_values)
    if rtype == "aws_ebs_snapshot":
        return EbsSnapshot(address, aws_region, raw_values)
    if rtype == "aws_ebs_snapshot_copy":
        return EbsSnapshotCopy(address, aws_region, raw_values)
    if rtype == "aws_launch_configuration":
        return Ec2LaunchConfiguration(address, aws_region, raw_values)
    if rtype == "aws_launch_template":
        return Ec2LaunchTemplate(address, aws_region, raw_values)
    if rtype == "aws_autoscaling_group":
        return Ec2AutoscalingGroup(address, aws_region, raw_values)
    return None  # unsupported -> skip


def parse_plan_file(file_path: str) -> List[Resource]:
    """
    Parse a Terraform plan JSON file and build a list of typed resources.
    Also wires up cross-resource references from configuration.expressions.
    """
    with open(file_path, "r") as f:
        plan = json.load(f)

    region = _aws_region(plan)

    # 1) Build resources map from planned_values
    resource_map: Dict[str, Resource] = {}
    pv_resources = (
        plan.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    for tr in pv_resources:
        address = tr.get("address", "")
        rtype = tr.get("type", "")
        raw_values = tr.get("values") or {}
        res = _create_resource(rtype, address, raw_values, region)
        if res is not None:
            resource_map[address] = res

    # 2) Wire references using configuration.root_module.resources[*].expressions
    cfg_resources = (
        plan.get("configuration", {})
        .get("root_module", {})
        .get("resources", [])
    )
    cfg_index = {r.get("address"): r for r in cfg_resources}

    for address, resource in resource_map.items():
        cfg = cfg_index.get(address) or {}
        _add_references(resource, cfg, resource_map)

    # Done — typed resources already build their subresources in their constructors
    return list(resource_map.values())


def _add_references(
    resource: Resource,
    resource_config: Dict[str, Any],
    resource_map: Dict[str, Resource],
) -> None:
    """
    Add references based on configuration.expressions.
    We look for:
      - direct: expressions.<key>.references[0]
      - id form: expressions.<key>[0].id.references[0]
    The reference key in the config becomes the reference name on the resource.
    """
    expressions = resource_config.get("expressions", {})
    if not isinstance(expressions, dict):
        return

    for key, value in expressions.items():
        ref_addr: Optional[str] = None

        # Case 1: direct references array
        if isinstance(value, dict) and "references" in value:
            refs = value.get("references") or []
            if isinstance(refs, list) and refs:
                ref_addr = refs[0]

        # Case 2: array with id.references
        elif isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                id_val = first.get("id")
                if isinstance(id_val, dict):
                    refs = id_val.get("references") or []
                    if isinstance(refs, list) and refs:
                        ref_addr = refs[0]

        if ref_addr and ref_addr in resource_map:
            # IMPORTANT: name the reference by the expression key
            # (e.g., "launch_template", "launch_configuration", "volume_id", etc.)
            resource.add_reference(key, resource_map[ref_addr])
