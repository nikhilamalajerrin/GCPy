from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from plancosts.config import resolve_endpoint
from plancosts.costs.breakdown import (
    ResourceCostBreakdown,
    generate_cost_breakdowns,
)
from plancosts.costs.query import GraphQLQueryRunner
from plancosts.parsers import terraform as tf_parser


_TF_PROVIDER_PREFIX = """
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
}
""".strip()


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stdout}")


def _generate_plan_json(
    workdir: Path,
    terraform_binary: Optional[str] = None,
) -> str:
    tfbin = terraform_binary or "terraform"
    _run([tfbin, "init", "-input=false", "-no-color"], workdir)
    _run([tfbin, "plan", "-out=plan.tfplan", "-input=false", "-no-color"], workdir)
    show = subprocess.run(
        [tfbin, "show", "-json", "plan.tfplan"],
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if show.returncode != 0:
        raise RuntimeError(f"terraform show failed:\n{show.stdout}")
    return show.stdout


def run_tf_cost_breakdown(
    resource_tf: str,
    *,
    api_url: Optional[str] = None,
    terraform_binary: Optional[str] = None,
) -> List[ResourceCostBreakdown]:
    tmpdir = Path(tempfile.mkdtemp(prefix="plancosts-test-"))
    try:
        (tmpdir / "main.tf").write_text(f"{_TF_PROVIDER_PREFIX}\n\n{resource_tf}\n", encoding="utf-8")
        plan_json = _generate_plan_json(tmpdir, terraform_binary)

        resources = tf_parser.parse_plan_json(plan_json)
        endpoint = resolve_endpoint(api_url)
        q = GraphQLQueryRunner(endpoint=endpoint)
        return generate_cost_breakdowns(q, resources)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_price_hashes(breakdowns: List[ResourceCostBreakdown]) -> List[List[str]]:
    """
    Returns [[resourceAddress, priceComponentName, priceHash], ...] in a stable,
    test-friendly order. For EC2 instances this ensures:
      - top-level instance entries first,
      - then root_block_device,
      - then ebs_block_device[n] in numeric order.
    """
    import re

    out: List[List[str]] = []

    def _walk(b: ResourceCostBreakdown) -> None:
        for pcc in b.price_component_costs:
            out.append([
                b.resource.address(),
                pcc.price_component.name(),
                getattr(pcc, "price_hash", "") or "",
            ])
        for sub in b.sub_resource_costs:
            _walk(sub)

    for b in breakdowns:
        _walk(b)

    def _addr_sort_key(addr: str) -> tuple:
        # Top-level instance (no sub-resource suffix) first
        if ".root_block_device" not in addr and ".ebs_block_device[" not in addr:
            return (0, 0, -1)  # group 0, subtype 0

        # root_block_device before any ebs block
        if ".root_block_device" in addr:
            return (1, 0, -1)  # group 1, subtype 0

        # ebs_block_device[n] in numeric order
        m = re.search(r"\.ebs_block_device\[(\d+)\]", addr)
        if m:
            return (1, 1, int(m.group(1)))  # group 1, subtype 1, index n

        # Fallback: after the above
        return (2, 0, -1)

    # Sort by our address key, then by component name for stability
    out.sort(key=lambda row: (_addr_sort_key(row[0]), row[1]))
    return out



def price_component_cost_for(
    breakdowns: List[ResourceCostBreakdown],
    resource_address: str,
    price_component_name: str,
):
    def _find(b: ResourceCostBreakdown):
        for pcc in b.price_component_costs:
            if b.resource.address() == resource_address and pcc.price_component.name() == price_component_name:
                return pcc
        for sub in b.sub_resource_costs:
            found = _find(sub)
            if found:
                return found
        return None

    for b in breakdowns:
        got = _find(b)
        if got:
            return got
    return None
