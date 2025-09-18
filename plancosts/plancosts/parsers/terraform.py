"""
Terraform plan parser that builds typed AWS Terraform resources.

Adds helpers to load/generate plan JSON like the Go commit:
- load_plan_json(path)
- generate_plan_json(tfpath, plan_path)
- parse_plan_json(plan_json)
"""
from __future__ import annotations

import json
import os
import tempfile
import subprocess
import logging
from typing import Dict, Any, List, Optional

from plancosts.base.resource import Resource  # type: ignore

# Typed AWS Terraform resources
from plancosts.providers.terraform.aws.ebs_volume import EbsVolume
from plancosts.providers.terraform.aws.ebs_snapshot import EbsSnapshot
from plancosts.providers.terraform.aws.ebs_snapshot_copy import EbsSnapshotCopy
from plancosts.providers.terraform.aws.ec2_instance import Ec2Instance
from plancosts.providers.terraform.aws.ec2_launch_configuration import Ec2LaunchConfiguration
from plancosts.providers.terraform.aws.ec2_launch_template import Ec2LaunchTemplate
from plancosts.providers.terraform.aws.ec2_autoscaling_group import Ec2AutoscalingGroup


# ---------------- Terraform execution helpers ----------------

def _run_tf(tfdir: str, *args: str) -> bytes:
    cmd = ["terraform", *args]
    logging.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=tfdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"Terraform command failed ({' '.join(cmd)}):\n{stderr}")
    return proc.stdout


def load_plan_json(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def generate_plan_json(tfpath: str | None, plan_path: str | None) -> bytes:
    if not tfpath:
        raise ValueError("--tfpath is required when generating plan JSON")

    # If no plan_path: init + plan to a temp file
    if not plan_path:
        _ = _run_tf(tfpath, "init", "-input=false", "-lock=false")
        with tempfile.NamedTemporaryFile(prefix="tfplan-", delete=False) as tmp:
            tmp_plan = tmp.name
        try:
            _ = _run_tf(
                tfpath, "plan",
                "-input=false", "-lock=false",
                f"-out={tmp_plan}"
            )
            out = _run_tf(tfpath, "show", "-json", tmp_plan)
        finally:
            try:
                os.remove(tmp_plan)
            except OSError:
                pass
        return out

    # If a binary plan is provided, just show -json it
    return _run_tf(tfpath, "show", "-json", plan_path)


# ---------------- JSON parsing into Resources ----------------

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
    rtype: str, address: str, raw_values: Dict[str, Any], aws_region: str
) -> Optional[Resource]:
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
    return None


def parse_plan_json(plan_json: bytes) -> List[Resource]:
    plan = json.loads(plan_json.decode("utf-8"))
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

    return [resource_map[k] for k in sorted(resource_map.keys())]


def parse_plan_file(file_path: str) -> List[Resource]:
    """Backward-compatible: read a plan JSON file from disk and parse."""
    return parse_plan_json(load_plan_json(file_path))


def _add_references(
    resource: Resource,
    resource_config: Dict[str, Any],
    resource_map: Dict[str, Resource],
) -> None:
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
            resource.add_reference(key, resource_map[ref_addr])
