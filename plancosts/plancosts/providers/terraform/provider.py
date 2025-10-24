from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Any

from plancosts.providers.terraform.cmd import load_plan_json, generate_plan_json
from plancosts.providers.terraform.parser import parse_plan_json


@dataclass
class TerraformProviderArgs:
    """
    Mirrors Go's CLI flag inputs:
      --tfjson  Path to Terraform plan in JSON format
      --tfplan  Path to Terraform binary plan file
      --tfdir   Path to Terraform project directory
    """
    tfjson: str = ""
    tfplan: str = ""
    tfdir: str = ""


class TerraformProvider:
    """
    Python equivalent of internal/providers/terraform/provider.go (terraformProvider).

    Usage:
        p = TerraformProvider()
        p.process_args(TerraformProviderArgs(tfjson="plan.json"))
        resources = p.load_resources()
    """

    def __init__(self) -> None:
        self.tfjson: str = ""
        self.tfplan: str = ""
        self.tfdir: str = ""

    # -------------------------------------------------------------
    # CLI argument handling (equivalent to ProcessArgs)
    # -------------------------------------------------------------
    def process_args(self, args: TerraformProviderArgs) -> None:
        """
        Validate and store CLI arguments.
        Raises ValueError for invalid argument combinations.
        """
        self.tfjson = args.tfjson or ""
        self.tfplan = args.tfplan or ""
        self.tfdir = args.tfdir or ""

        if self.tfjson and self.tfplan:
            raise ValueError(
                "Please provide either a Terraform Plan JSON file (tfjson) "
                "or a Terraform Plan file (tfplan), not both."
            )

        if self.tfplan and not self.tfdir:
            raise ValueError(
                "Please provide a path to the Terraform project (tfdir) "
                "if providing a Terraform Plan file (tfplan)."
            )

        # Optional guard: ensure at least one source is defined
        if not (self.tfjson or self.tfplan or self.tfdir):
            raise ValueError(
                "Please provide either the path to the Terraform project (tfdir) "
                "or a Terraform Plan JSON file (tfjson)."
            )

    # -------------------------------------------------------------
    # Plan loading (equivalent to LoadResources)
    # -------------------------------------------------------------
    def load_resources(self) -> List[Any]:
        """
        Load and parse Terraform resources from a plan or directory.
        Returns a list of schema.Resource-like objects.
        """
        if self.tfjson:
            plan_bytes = load_plan_json(self.tfjson)
        else:
            plan_bytes = generate_plan_json(self.tfdir, self.tfplan or "")

        resources = parse_plan_json(plan_bytes)
        return resources


# Optional alias for parity with Go style
Provider = TerraformProvider
