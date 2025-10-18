from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .cmd import load_plan_json, generate_plan_json
from .parser import parse_plan_json  # <-- fixed: was `.provider`

@dataclass
class TerraformProviderArgs:
    tfjson: str = ""
    tfplan: str = ""
    tfdir: str = ""

class TerraformProvider:
    def __init__(self) -> None:
        self.tfjson = ""
        self.tfplan = ""
        self.tfdir = ""

    # Parity with Go's ProcessArgs: validate combinations
    def process_args(self, args: TerraformProviderArgs) -> None:
        self.tfjson = args.tfjson or ""
        self.tfplan = args.tfplan or ""
        self.tfdir = args.tfdir or ""

        if self.tfjson and self.tfplan:
            raise ValueError(
                "Please only provide one of either a Terraform Plan JSON file (tfjson) or a Terraform Plan file (tfplan)"
            )

        if self.tfplan and not self.tfdir:
            raise ValueError(
                "Please provide a path to the Terraform project (tfdir) if providing a Terraform Plan file (tfplan)\n\n"
            )

        if not self.tfjson and not self.tfdir:
            raise ValueError(
                "Please provide either the path to the Terraform project (tfdir) or a Terraform Plan JSON file (tfjson)"
            )

    # Parity with Go's LoadResources
    def load_resources(self):
        if self.tfjson:
            plan_bytes = load_plan_json(self.tfjson)
        else:
            plan_bytes = generate_plan_json(self.tfdir, self.tfplan or None)

        # Your parser returns a list of typed resources
        resources = parse_plan_json(plan_bytes)
        return resources
