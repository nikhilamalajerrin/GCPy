# tests/util/testutil.py
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pytest

from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.costs.breakdown import generate_cost_breakdowns
from plancosts.costs.query import GraphQLQueryRunner
from plancosts.parsers.terraform import generate_plan_json, parse_plan_json  # if your project exposes these

PROVIDER_PREFIX = """
provider "aws" {
  region                      = "us-east-1"
  s3_force_path_style         = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
}
""".strip()


def _have_terraform() -> bool:
    return shutil.which(os.getenv("TERRAFORM_BINARY", "terraform")) is not None


def run_tf_cost_breakdown(hcl_body: str):
    """
    Write a temp TF project (provider stub + user HCL), run Terraform to
    produce plan JSON, parse resources, then compute breakdowns via the
    GraphQLQueryRunner pointing at PRICE_LIST_API_ENDPOINT.
    """
    if not _have_terraform():
        pytest.skip("Terraform is not available on PATH; skipping integration test.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "main.tf").write_text(PROVIDER_PREFIX + "\n\n" + hcl_body)

        # If you already have wrappers for these in your project, prefer them.
        # Here we call the same functions your CLI uses.
        plan_json = generate_plan_json(str(tmp_path), var_file="")
        resources = parse_plan_json(plan_json)

        runner = GraphQLQueryRunner(PRICE_LIST_API_ENDPOINT)
        breakdowns = generate_cost_breakdowns(runner, resources)
        return breakdowns


def extract_price_hashes(breakdowns) -> List[List[str]]:
    """Return [[resourceAddress, priceComponentName, priceHash], …]"""
    out: List[List[str]] = []

    def _walk(bd):
        for pc_cost in bd.price_component_costs:
            out.append([bd.resource.address(), pc_cost.price_component.name(), pc_cost.price_hash])
        for sub in bd.sub_resource_costs:
            _walk(sub)

    for bd in breakdowns:
        _walk(bd)
    # Sort deterministically like cmpopts.SortSlices in Go test
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def find_price_component_cost(breakdowns, resource_address: str, price_component_name: str):
    """Return the PriceComponentCost for (resource_address, price_component_name) or None."""
    def _walk(bd):
        if bd.resource.address() == resource_address:
            for pc_cost in bd.price_component_costs:
                if pc_cost.price_component.name() == price_component_name:
                    return pc_cost
        for sub in bd.sub_resource_costs:
            r = _walk(sub)
            if r is not None:
                return r
        return None

    for bd in breakdowns:
        r = _walk(bd)
        if r is not None:
            return r
    return None
