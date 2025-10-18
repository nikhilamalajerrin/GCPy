# tests/util/tftest.py
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Iterable, List, Optional

from plancosts.providers.terraform.parser import parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.base.costs import get_cost_breakdowns

# Mirrors the Go helper’s provider boilerplate (kept for parity/documentation).
# Not strictly required since we ingest plan JSON directly in tests.
TF_PROVIDERS = """
provider "aws" {
  region                      = "us-east-1"
  s3_force_path_style         = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  access_key                  = "mock_access_key"
  secret_key                  = "mock_secret_key"
}

provider "infracost" {}
""".strip()


def WithProviders(tf: str) -> str:
    """Return TF config with provider stubs prepended (parity with Go)."""
    return f"{TF_PROVIDERS}\n{tf}"


@dataclass
class TerraformFile:
    path: str
    contents: str


def _write_to_tmp_dir(terraform_files: Iterable[TerraformFile]) -> str:
    """
    Create a temp directory and write the provided files there.
    (We don’t actually run terraform; this is parity with Go helper shape.)
    """
    td = tempfile.mkdtemp(prefix="plancosts_")
    for f in terraform_files:
        full = os.path.join(td, f.path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(f.contents)
    return td


def _load_plan_from_terraform_files(terraform_files: Iterable[TerraformFile]) -> dict:
    """
    Find a Terraform plan JSON among the provided files and return it as a dict.

    Priority:
      1) a file literally named 'plan.json'
      2) first file whose contents parse as JSON
    """
    for f in terraform_files:
        if os.path.basename(f.path) == "plan.json":
            return json.loads(f.contents)

    for f in terraform_files:
        try:
            return json.loads(f.contents)
        except Exception:
            continue

    raise ValueError(
        "No Terraform plan JSON provided. "
        "Add a TerraformFile with path='plan.json' (or any *.json) containing the plan."
    )


def LoadResources(tf_plan_json: str | dict) -> List[object]:
    """
    Parse a Terraform plan JSON string/dict into provider resources (AwsInstance, etc.).
    """
    plan = json.loads(tf_plan_json) if isinstance(tf_plan_json, str) else tf_plan_json
    return parse_plan_json(plan)


def LoadResourcesForProject(terraform_files: List[TerraformFile]) -> List[object]:
    """
    Parity with the Go helper: accept a list of files, locate/read the plan JSON,
    and parse it into provider resources.
    """
    _write_to_tmp_dir(terraform_files)  # keeps the call shape similar to Go
    plan = _load_plan_from_terraform_files(terraform_files)
    return parse_plan_json(plan)


def RunCostCalculation(
    tf_plan_json: str | dict,
    graphql_endpoint: str = "http://127.0.0.1:4000/graphql",
    timeout: Optional[float] = 30.0,
) -> List[object]:
    """
    End-to-end: plan JSON -> resources -> price via GraphQL -> return priced resources.

    Mirrors the Go flow:
      resources := LoadResources(...)
      prices.PopulatePrices(resources)
      schema.CalculateCosts(resources)
    """
    resources = LoadResources(tf_plan_json)
    runner = GraphQLQueryRunner(graphql_endpoint, timeout=timeout)
    get_cost_breakdowns(runner, resources)  # sets unit prices & price hashes in-place
    return resources
