"""
Terraform plan parser that builds typed AWS Terraform resources.

Adds helpers to load/generate plan JSON like the Go commit:
- load_plan_json(path)
- generate_plan_json(tfdir, plan_path)
- parse_plan_json(plan_json)

Commit 9c5c9f1 parity:
- Support Terraform modules: recursively parse `planned_values.root_module.child_modules[*]`
- For each child module, find its config at `configuration.root_module.module_calls.<name>.module`
- Use a module-qualified address for resources (e.g. "module.web_app[us-east-1a].aws_instance.web")
- Wire references WITHIN each module using the module-internal addresses found in expressions
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from plancosts.base.resource import Resource  # type: ignore
from plancosts.providers.terraform.aws.ebs_snapshot import EbsSnapshot
from plancosts.providers.terraform.aws.ebs_snapshot_copy import EbsSnapshotCopy

# Typed AWS Terraform resources
from plancosts.providers.terraform.aws.ebs_volume import EbsVolume
from plancosts.providers.terraform.aws.ec2_autoscaling_group import Ec2AutoscalingGroup
from plancosts.providers.terraform.aws.ec2_instance import Ec2Instance
from plancosts.providers.terraform.aws.ec2_launch_configuration import (
    Ec2LaunchConfiguration,
)
from plancosts.providers.terraform.aws.ec2_launch_template import Ec2LaunchTemplate
from plancosts.providers.terraform.aws.elb import Elb
from plancosts.providers.terraform.aws.nat_gateway import NatGateway
from plancosts.providers.terraform.aws.rds_instance import RdsInstance

# ---------------- Terraform execution helpers ----------------


def _run_tf(tfdir: str, *args: str) -> bytes:
    tf_bin = os.getenv("TERRAFORM_BINARY") or "terraform"
    cmd = [tf_bin, *args]
    logging.info("Running: %s (cwd=%s)", " ".join(cmd), tfdir)
    proc = subprocess.run(
        cmd, cwd=tfdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Terraform command failed ({' '.join(cmd)}):\n{stderr}")
    return proc.stdout


def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def generate_plan_json(tfdir: str | None, plan_path: str | None) -> bytes:
    if not tfdir:
        raise ValueError("--tfdir is required when generating plan JSON")

    # If no plan_path: init + plan to a temp file
    if not plan_path:
        _ = _run_tf(tfdir, "init", "-input=false", "-lock=false")
        with tempfile.NamedTemporaryFile(prefix="tfplan-", delete=False) as tmp:
            tmp_plan = tmp.name
        try:
            _ = _run_tf(
                tfdir, "plan", "-input=false", "-lock=false", f"-out={tmp_plan}"
            )
            out = _run_tf(tfdir, "show", "-json", tmp_plan)
        finally:
            try:
                os.remove(tmp_plan)
            except OSError:
                pass
        return out

    # If a binary plan is provided, just show -json it
    return _run_tf(tfdir, "show", "-json", plan_path)


# ---------------- Region resolution ----------------


def _aws_region_from_provider(plan_obj: Dict[str, Any]) -> str:
    """
    Reads provider aws.expressions.region.constant_value if present.
    """
    if not isinstance(plan_obj, dict):
        return ""
    return (
        plan_obj.get("configuration", {})
        .get("provider_config", {})
        .get("aws", {})
        .get("expressions", {})
        .get("region", {})
        .get("constant_value", "")
    )


def _region_from_arn(arn: str) -> str:
    """
    ARN format: arn:partition:service:region:account-id:resource
    Return the region token (index 3) when present.
    """
    try:
        parts = arn.split(":")
        if len(parts) > 3 and parts[3]:
            return parts[3]
    except Exception:
        pass
    return ""


def _select_region(provider_region: str, raw_values: Dict[str, Any]) -> str:
    """
    Implements Infracost commit 7a1dfe3 logic:
    - Default/fallback to us-east-1
    - Use provider config region if set
    - Override with region parsed from values.arn when present
    """
    region = provider_region or "us-east-1"
    arn = raw_values.get("arn")
    if isinstance(arn, str) and arn:
        arn_region = _region_from_arn(arn)
        if arn_region:
            region = arn_region
    return region


# ---------------- JSON parsing into Resources ----------------


def _create_resource(
    rtype: str, address: str, raw_values: Dict[str, Any], provider_region: str
) -> Optional[Resource]:
    # Region per-resource: provider fallback → override from arn if present
    aws_region = _select_region(provider_region, raw_values)

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
    if rtype == "aws_elb":
        return Elb(address, aws_region, raw_values, is_classic=True)
    if rtype in ("aws_lb", "aws_alb"):  # alb is an alias for lb
        return Elb(address, aws_region, raw_values, is_classic=False)
    if rtype == "aws_nat_gateway":
        return NatGateway(address, aws_region, raw_values)
    if rtype == "aws_db_instance":
        return RdsInstance(address, aws_region, raw_values)
    return None


def parse_plan_json(plan_json: bytes | str | Dict[str, Any]) -> List[Resource]:
    """
    Accepts bytes (preferred), str (JSON), or a pre-parsed dict.
    Returns a list of typed Resource objects with module-qualified addresses.
    """
    # Normalize to a dict
    if isinstance(plan_json, (bytes, bytearray)):
        try:
            plan_obj = json.loads(plan_json.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid plan JSON bytes: {e}")
    elif isinstance(plan_json, str):
        try:
            plan_obj = json.loads(plan_json)
        except Exception as e:
            raise ValueError(f"Invalid plan JSON string: {e}")
    elif isinstance(plan_json, dict):
        plan_obj = plan_json
    else:
        raise TypeError(
            f"parse_plan_json expected bytes|str|dict, got {type(plan_json).__name__}"
        )

    if callable(plan_obj):
        # Very explicit guard for the "'function' object has no attribute 'get'" case
        raise TypeError("parse_plan_json received a function instead of JSON data")

    provider_region = _aws_region_from_provider(plan_obj)

    root_pv = plan_obj.get("planned_values", {}).get("root_module", {})
    root_cfg = plan_obj.get("configuration", {}).get("root_module", {})

    resources: List[Resource] = []
    _parse_module(
        plan_obj, provider_region, root_pv, root_cfg, module_addr="", out_list=resources
    )
    # Sort by address for stable output
    return sorted(resources, key=lambda r: r.address())


def parse_plan_file(file_path: str) -> List[Resource]:
    """Backward-compatible: read a plan JSON file from disk and parse."""
    return parse_plan_json(load_plan_json(file_path))


# -------- Module parsing helpers (commit 9c5c9f1 parity) --------

_MODULE_RE = re.compile(r"module\.([^[]+)")


def _parse_module_name(module_addr: str) -> str:
    """
    Extract module call name from a child module address like:
      module.web_app["us-east-1a"]  -> "web_app"
      module.storage[0]             -> "storage"
    """
    if not module_addr:
        return "root_module"
    m = _MODULE_RE.search(module_addr)
    return m.group(1) if m and m.group(1) else ""


def _parse_module(
    plan_obj: Dict[str, Any],
    provider_region: str,
    planned_values_module: Dict[str, Any],
    config_module: Dict[str, Any],
    module_addr: str,
    out_list: List[Resource],
) -> None:
    """
    Parse a (sub)module:
    - Create resources with module-qualified addresses (module_addr + "." + internal address)
    - Wire references within this module using internal addresses from `expressions`
    - Recurse into child_modules
    """
    # 1) Build resources from this module's planned values
    pv_resources = planned_values_module.get("resources") or []
    local_map: Dict[str, Resource] = {}  # internal address -> Resource

    for tr in pv_resources:
        internal_addr = tr.get("address", "")
        rtype = tr.get("type", "")
        raw_values = tr.get("values") or {}

        # Compose module-qualified address for display/uniqueness
        full_addr = f"{module_addr}.{internal_addr}" if module_addr else internal_addr

        res = _create_resource(rtype, full_addr, raw_values, provider_region)
        if res is not None:
            local_map[internal_addr] = res
            out_list.append(res)

    # 2) Wire references within this module using its config
    cfg_resources = config_module.get("resources") or []
    cfg_index = {r.get("address"): r for r in cfg_resources}

    for internal_addr, res in local_map.items():
        _add_references(res, cfg_index.get(internal_addr) or {}, local_map)

    # 3) Recurse into child modules (if any)
    for child in planned_values_module.get("child_modules") or []:
        child_addr = child.get("address", "") or ""
        module_name = _parse_module_name(child_addr)
        # Find the child module's config under module_calls.<name>.module
        child_cfg = {}
        if module_name:
            child_cfg = (
                (config_module.get("module_calls") or {}).get(module_name) or {}
            ).get("module") or {}

        # Recurse: module_addr grows (use the child module address verbatim to match TF output)
        next_module_addr = (
            child_addr if module_addr == "" else f"{module_addr}.{child_addr}"
        )
        _parse_module(
            plan_obj, provider_region, child, child_cfg, next_module_addr, out_list
        )


def _add_references(
    resource: Resource,
    resource_config: Dict[str, Any],
    scope_map: Dict[str, Resource],
) -> None:
    """
    Within a module, `expressions.*.references` list uses INTERNAL addresses (no module prefix).
    Resolve against `scope_map` (the module-local resource map).
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

        if ref_addr and ref_addr in scope_map:
            resource.add_reference(key, scope_map[ref_addr])
