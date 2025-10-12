from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plancosts.resource.resource import Resource, BaseResource

# Typed AWS resources
from plancosts.providers.terraform.aws.ec2_instance import Ec2Instance
from plancosts.providers.terraform.aws.ebs_volume import EbsVolume
from plancosts.providers.terraform.aws.ebs_snapshot import EbsSnapshot
from plancosts.providers.terraform.aws.ebs_snapshot_copy import EbsSnapshotCopy
from plancosts.providers.terraform.aws.ec2_launch_configuration import Ec2LaunchConfiguration
from plancosts.providers.terraform.aws.ec2_launch_template import Ec2LaunchTemplate
from plancosts.providers.terraform.aws.ec2_autoscaling_group import Ec2AutoscalingGroup
from plancosts.providers.terraform.aws.rds_instance import RdsInstance
from plancosts.providers.terraform.aws.elb import Elb
from plancosts.providers.terraform.aws.nat_gateway import NatGateway
from plancosts.providers.terraform.aws.dynamodb_table import DynamoDBTable
from plancosts.providers.terraform.aws.ecs_service import EcsService  # Fargate

from .cmd import load_plan_json as _load_plan_json
from .address import (
    parse_module_name,
    strip_address_array,
    qualify,
)

__all__ = ["parse_plan_json", "parse_plan_file"]


# ---------------- Region helpers ----------------

def _provider_region(plan_obj: Dict[str, Any]) -> str:
    return (
        plan_obj.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )

def _region_from_arn(arn: str) -> str:
    try:
        parts = arn.split(":")
        if len(parts) > 3 and parts[3]:
            return parts[3]
    except Exception:
        pass
    return ""

def _select_region(provider_region: str, raw: Dict[str, Any]) -> str:
    region = provider_region or "us-east-1"
    arn = raw.get("arn")
    if isinstance(arn, str) and arn:
        arn_region = _region_from_arn(arn)
        if arn_region:
            region = arn_region
    return region


# ---------------- Resource creation ----------------

def _create_resource(
    resource_type: str,
    address: str,
    raw: Dict[str, Any],
    provider_region: str,
) -> Optional[Resource]:
    aws_region = _select_region(provider_region, raw)

    if resource_type == "aws_instance":
        return Ec2Instance(address, aws_region, raw)
    if resource_type == "aws_ebs_volume":
        return EbsVolume(address, aws_region, raw)
    if resource_type == "aws_ebs_snapshot":
        return EbsSnapshot(address, aws_region, raw)
    if resource_type == "aws_ebs_snapshot_copy":
        return EbsSnapshotCopy(address, aws_region, raw)

    # IMPORTANT: do NOT force has_cost=False; ASG wraps these components.
    if resource_type == "aws_launch_configuration":
        return Ec2LaunchConfiguration(address, aws_region, raw)

    if resource_type == "aws_launch_template":
        return Ec2LaunchTemplate(address, aws_region, raw)

    if resource_type == "aws_autoscaling_group":
        return Ec2AutoscalingGroup(address, aws_region, raw)

    if resource_type == "aws_db_instance":
        return RdsInstance(address, aws_region, raw)

    if resource_type == "aws_elb":
        return Elb(address, aws_region, raw, is_classic=True)
    if resource_type in ("aws_lb", "aws_alb"):
        return Elb(address, aws_region, raw, is_classic=False)

    if resource_type == "aws_nat_gateway":
        return NatGateway(address, aws_region, raw)

    if resource_type == "aws_dynamodb_table":
        return DynamoDBTable(address, aws_region, raw)

    if resource_type == "aws_ecs_service":
        return EcsService(address, aws_region, raw)

    # Read by ecs_service; no direct cost.
    if resource_type == "aws_ecs_task_definition":
        return BaseResource(address, raw, has_cost=False)

    return None


# ---------------- Parse plan JSON ----------------

def parse_plan_json(plan_json: bytes | str | Dict[str, Any]) -> List[Resource]:
    if isinstance(plan_json, (bytes, bytearray)):
        plan = json.loads(plan_json.decode("utf-8"))
    elif isinstance(plan_json, str):
        plan = json.loads(plan_json)
    elif isinstance(plan_json, dict):
        plan = plan_json
    else:
        raise TypeError(
            f"parse_plan_json expected bytes|str|dict, got {type(plan_json).__name__}"
        )

    provider_region = _provider_region(plan)

    root_pv = plan.get("planned_values", {}).get("root_module", {}) or {}
    root_cfg = plan.get("configuration", {}).get("root_module", {}) or {}

    resources: List[Resource] = []
    # global map for fully-qualified lookups across modules
    global_map: Dict[str, Resource] = {}

    _parse_module(
        plan,
        provider_region,
        root_pv,
        root_cfg,
        module_addr="",
        out_list=resources,
        global_map=global_map,
    )
    return sorted(resources, key=lambda r: r.address())


def parse_plan_file(path: str) -> List[Resource]:
    return parse_plan_json(_load_plan_json(path))


# ---------------- Module parsing & references ----------------

def _get_internal_name(resource_addr: str, module_addr: str) -> str:
    """Return address without the module prefix so we can match config resources."""
    if not module_addr:
        return resource_addr
    prefix = module_addr + "."
    return resource_addr[len(prefix):] if resource_addr.startswith(prefix) else resource_addr


def _add_references_helper(
    r: Resource,
    key: str,
    value: Any,
    local_map: Dict[str, Resource],
    global_map: Dict[str, Resource],
    module_addr: str,
) -> None:
    """
    Walk configuration JSON expressions tree to find "references" arrays and
    connect them to resources (preferring local module, then fully-qualified).
    """
    ref_addr = None

    # {"references": ["addr", ...]}
    if isinstance(value, dict) and isinstance(value.get("references"), list) and value["references"]:
        ref_addr = value["references"][0]
    # [{"id": {"references": ["addr", ...]}}]
    elif isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            id_node = first.get("id")
            if isinstance(id_node, dict) and isinstance(id_node.get("references"), list) and id_node["references"]:
                ref_addr = id_node["references"][0]

    if ref_addr:
        # local (unqualified)
        if ref_addr in local_map:
            r.add_reference(key, local_map[ref_addr])
            return
        # fully-qualified under current module path
        fq = qualify(module_addr, ref_addr)
        target = global_map.get(fq)
        if target is not None:
            r.add_reference(key, target)
            return

    # Recurse nested JSON
    if isinstance(value, dict):
        for k, v in value.items():
            _add_references_helper(r, k, v, local_map, global_map, module_addr)
    elif isinstance(value, list):
        for item in value:
            _add_references_helper(r, key, item, local_map, global_map, module_addr)


def _add_references(
    r: Resource,
    resource_json: Dict[str, Any],
    local_map: Dict[str, Resource],
    global_map: Dict[str, Resource],
    module_addr: str,
) -> None:
    expressions = resource_json.get("expressions")
    if isinstance(expressions, dict):
        _add_references_helper(r, "expressions", expressions, local_map, global_map, module_addr)


def _parse_module(
    plan: Dict[str, Any],
    provider_region: str,
    planned_values_module: Dict[str, Any],
    config_module: Dict[str, Any],
    module_addr: str,
    out_list: List[Resource],
    global_map: Dict[str, Resource],
) -> None:
    # 1) Build local resources
    terraform_resources = planned_values_module.get("resources") or []
    local_map: Dict[str, Resource] = {}

    for tr in terraform_resources:
        addr = tr.get("address", "")
        rtype = tr.get("type", "")
        values = tr.get("values") if isinstance(tr.get("values"), dict) else {}
        full_addr = f"{module_addr}.{addr}" if module_addr else addr

        res = _create_resource(rtype, full_addr, values or {}, provider_region)
        if res is not None:
            internal = _get_internal_name(full_addr, module_addr)
            local_map[internal] = res
            out_list.append(res)
            global_map[full_addr] = res

    # 2) Wire references using configuration module resources[*].expressions
    cfg_resources = config_module.get("resources") or []
    for res in local_map.values():
        internal = _get_internal_name(res.address(), module_addr)
        internal_stripped = strip_address_array(internal)

        # Match either exact 'address' or array-stripped
        cfg_json = next(
            (
                rj for rj in cfg_resources
                if rj.get("address") == internal or rj.get("address") == internal_stripped
            ),
            {}
        )

        _add_references(res, cfg_json, local_map, global_map, module_addr)

        # --- explicit ECS task_definition safety net (some TF shapes are odd) ---
        if isinstance(res, EcsService):
            try:
                expr = (cfg_json.get("expressions") or {}).get("task_definition")
                ref_addr = None
                if isinstance(expr, dict) and isinstance(expr.get("references"), list) and expr["references"]:
                    ref_addr = expr["references"][0]
                if ref_addr:
                    target = local_map.get(ref_addr) or global_map.get(qualify(module_addr, ref_addr))
                    if target:
                        res.add_reference("task_definition", target)
            except Exception:
                pass
        # -----------------------------------------------------------------------

        # --- explicit ASG launch_template/launch_configuration safety net ---
        if isinstance(res, Ec2AutoscalingGroup):
            try:
                # DFS over the expressions tree and collect all reference strings
                exprs = (cfg_json.get("expressions") or {})
                stack = [exprs]
                refs: List[str] = []
                while stack:
                    node = stack.pop()
                    if isinstance(node, dict):
                        rlist = node.get("references")
                        if isinstance(rlist, list):
                            refs.extend([s for s in rlist if isinstance(s, str)])
                        for v in node.values():
                            stack.append(v)
                    elif isinstance(node, list):
                        for v in node:
                            stack.append(v)

                chosen = None
                for s in refs:
                    if s.startswith("aws_launch_template."):
                        chosen = s
                        break
                if not chosen:
                    for s in refs:
                        if s.startswith("aws_launch_configuration."):
                            chosen = s
                            break

                if chosen:
                    target = local_map.get(chosen) or global_map.get(qualify(module_addr, chosen))
                    if target:
                        keyname = (
                            "launch_template" if chosen.startswith("aws_launch_template.")
                            else "launch_configuration"
                        )
                        res.add_reference(keyname, target)
            except Exception:
                pass
        # -----------------------------------------------------------------------

    # 3) Recurse into child modules
    for child in planned_values_module.get("child_modules") or []:
        child_addr = child.get("address", "") or ""
        module_name = parse_module_name(child_addr)

        child_cfg = {}
        if module_name:
            child_cfg = (
                (config_module.get("module_calls") or {}).get(module_name) or {}
            ).get("module") or {}

        next_module_addr = child_addr if not module_addr else f"{module_addr}.{child_addr}"
        _parse_module(
            plan,
            provider_region,
            child,
            child_cfg,
            next_module_addr,
            out_list,
            global_map,
        )
