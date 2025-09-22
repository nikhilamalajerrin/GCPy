# plancosts/parsers/terraform.py
"""
Python port of pkg/parsers/terraform/terraform.go (before the later "resource" package split).

- Uses provider-config region, overridden by ARN region if present.
- Creates typed AWS resources via plancosts.providers.terraform.aws.* constructors.
- Recursively parses child modules and wires references found in configuration.*.resources[*].expressions
  (supports both {"references":[...]} and [{"id":{"references":[...]}}] shapes).
- Top-level LC/LT are created with has_cost=False only if your class signatures require it; otherwise plain (address, region, raw_values).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from plancosts.base.resource import Resource  # your existing base interfaces

# Typed AWS resources (match your earlier Python files under providers/terraform/aws)
from plancosts.providers.terraform.aws.ec2_instance import Ec2Instance
from plancosts.providers.terraform.aws.ebs_volume import EbsVolume
from plancosts.providers.terraform.aws.ebs_snapshot import EbsSnapshot
from plancosts.providers.terraform.aws.ebs_snapshot_copy import EbsSnapshotCopy
from plancosts.providers.terraform.aws.ec2_launch_configuration import (
    Ec2LaunchConfiguration,
)
from plancosts.providers.terraform.aws.ec2_launch_template import Ec2LaunchTemplate
from plancosts.providers.terraform.aws.ec2_autoscaling_group import (
    Ec2AutoscalingGroup,
)
from plancosts.providers.terraform.aws.rds_instance import RdsInstance
from plancosts.providers.terraform.aws.elb import Elb
from plancosts.providers.terraform.aws.nat_gateway import NatGateway


# ---------------- Terraform command helpers ----------------

def _run_tf(tfdir: str, *args: str) -> bytes:
    terraform_binary = os.getenv("TERRAFORM_BINARY") or "terraform"
    cmd = [terraform_binary, *args]
    proc = subprocess.run(
        cmd, cwd=tfdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Terraform command failed: {' '.join(cmd)}\n{proc.stderr.decode('utf-8', 'ignore')}"
        )
    return proc.stdout


def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def generate_plan_json(tfdir: str, plan_path: str | None) -> bytes:
    if not tfdir:
        raise ValueError("--tfdir is required to generate plan JSON")

    if not plan_path:
        # terraform init
        _run_tf(tfdir, "init")
        # terraform plan -out=<tmp>
        with tempfile.NamedTemporaryFile(prefix="tfplan-", delete=False) as tmp:
            tmp_plan = tmp.name
        try:
            _run_tf(tfdir, "plan", "-input=false", "-lock=false", f"-out={tmp_plan}")
            out = _run_tf(tfdir, "show", "-json", tmp_plan)
        finally:
            try:
                os.remove(tmp_plan)
            except OSError:
                pass
        return out

    # If plan_path exists, show -json it
    return _run_tf(tfdir, "show", "-json", plan_path)


# ---------------- Region helpers ----------------

def _provider_region(plan_obj: Dict[str, Any]) -> str:
    # configuration.provider_config.aws.expressions.region.constant_value
    return (
        plan_obj.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )


def _region_from_arn(arn: str) -> str:
    # arn:partition:service:region:account-id:resource
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

def _create_resource(resource_type: str, address: str, raw: Dict[str, Any], provider_region: str) -> Optional[Resource]:
    aws_region = _select_region(provider_region, raw)

    if resource_type == "aws_instance":
        return Ec2Instance(address, aws_region, raw)
    if resource_type == "aws_ebs_volume":
        return EbsVolume(address, aws_region, raw)
    if resource_type == "aws_ebs_snapshot":
        return EbsSnapshot(address, aws_region, raw)
    if resource_type == "aws_ebs_snapshot_copy":
        return EbsSnapshotCopy(address, aws_region, raw)
    if resource_type == "aws_launch_configuration":
        # If your Ec2LaunchConfiguration signature requires has_cost, pass it here:
        try:
            return Ec2LaunchConfiguration(address, aws_region, raw, has_cost=False)
        except TypeError:
            return Ec2LaunchConfiguration(address, aws_region, raw)
    if resource_type == "aws_launch_template":
        try:
            return Ec2LaunchTemplate(address, aws_region, raw, has_cost=False)
        except TypeError:
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

    return None


# ---------------- Parse plan JSON ----------------

def parse_plan_json(plan_json: bytes | str | Dict[str, Any]) -> List[Resource]:
    # Normalize input
    if isinstance(plan_json, (bytes, bytearray)):
        plan = json.loads(plan_json.decode("utf-8"))
    elif isinstance(plan_json, str):
        plan = json.loads(plan_json)
    elif isinstance(plan_json, dict):
        plan = plan_json
    else:
        raise TypeError(f"parse_plan_json expected bytes|str|dict, got {type(plan_json).__name__}")

    provider_region = _provider_region(plan)

    root_pv = plan.get("planned_values", {}).get("root_module", {}) or {}
    root_cfg = plan.get("configuration", {}).get("root_module", {}) or {}

    resources: List[Resource] = []
    _parse_module(plan, provider_region, root_pv, root_cfg, module_addr="", out_list=resources)
    # Stable ordering
    return sorted(resources, key=lambda r: r.address())


def parse_plan_file(path: str) -> List[Resource]:
    return parse_plan_json(load_plan_json(path))


# ---------------- Module parsing & references ----------------

_MODULE_RE = re.compile(r"module\.([^[]+)")

def _parse_module_name(module_addr: str) -> str:
    if not module_addr:
        return "root_module"
    m = _MODULE_RE.search(module_addr)
    return m.group(1) if m and m.group(1) else ""


def _get_internal_name(resource_addr: str, module_addr: str) -> str:
    # Trim "module.<...>." prefix like the Go helper getInternalName
    if not module_addr:
        return resource_addr
    prefix = module_addr + "."
    return resource_addr[len(prefix):] if resource_addr.startswith(prefix) else resource_addr


# --- recursive helper like Go's addReferencesHelper ---

def _add_references_helper(r: Resource, key: str, value: Any, resource_map: Dict[str, Resource]) -> None:
    ref_addr = None

    # Shape A: {"references": ["addr", ...]}
    if isinstance(value, dict) and isinstance(value.get("references"), list) and value["references"]:
        ref_addr = value["references"][0]

    # Shape B: [{"id": {"references": ["addr", ...]}}]
    elif isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            id_node = first.get("id")
            if isinstance(id_node, dict) and isinstance(id_node.get("references"), list) and id_node["references"]:
                ref_addr = id_node["references"][0]

    if ref_addr and ref_addr in resource_map:
        r.add_reference(key, resource_map[ref_addr])
        return

    # Recurse into nested JSON (mirrors Go's valueJSON.Type == "JSON")
    if isinstance(value, dict):
        for k, v in value.items():
            _add_references_helper(r, k, v, resource_map)


def _add_references(r: Resource, resource_json: Dict[str, Any], resource_map: Dict[str, Resource]) -> None:
    expressions = resource_json.get("expressions")
    if isinstance(expressions, dict):
        _add_references_helper(r, "expressions", expressions, resource_map)



def _parse_module(
    plan: Dict[str, Any],
    provider_region: str,
    planned_values_module: Dict[str, Any],
    config_module: Dict[str, Any],
    module_addr: str,
    out_list: List[Resource],
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
            local_map[_get_internal_name(full_addr, module_addr)] = res
            out_list.append(res)

    # 2) Wire references using configuration module resources[*].expressions
    cfg_resources = config_module.get("resources") or []
    for res in local_map.values():
        internal = _get_internal_name(res.address(), module_addr)
        cfg_json = next((r for r in cfg_resources if r.get("address") == internal), {})
        _add_references(res, cfg_json, local_map)

    # 3) Recurse into child modules
    for child in planned_values_module.get("child_modules") or []:
        child_addr = child.get("address", "") or ""
        module_name = _parse_module_name(child_addr)
        child_cfg = {}
        if module_name:
            child_cfg = (
                (config_module.get("module_calls") or {}).get(module_name) or {}
            ).get("module") or {}

        next_module_addr = child_addr if not module_addr else f"{module_addr}.{child_addr}"
        _parse_module(plan, provider_region, child, child_cfg, next_module_addr, out_list)
