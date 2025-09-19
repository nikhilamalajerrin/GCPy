#!/usr/bin/env bash
set -euo pipefail

PREFIX="${1:-run}"

# Required env by workflow:
#   TERRAFORM_DIR: path inside the repo containing Terraform code (e.g. infra/)
# Optional env:
#   PLANCOSTS_API_URL: override pricing API (defaults handled by app)
#   TFPLAN_JSON: if present, run against this JSON instead of directory

cd /github/workspace

run_plancosts() {
  if [[ -n "${TFPLAN_JSON:-}" ]]; then
    python3 main.py --tfjson "$TFPLAN_JSON" -o table
  else
    # Run against a directory; main.py will call terraform for you
    python3 main.py --tfdir "$TERRAFORM_DIR" -o table
  fi
}

output="$(run_plancosts || true)"
echo "$output"
echo "$output" > "${PREFIX}-plancosts.txt"

# Extract the last column on the OVERALL TOTAL line
monthly_cost="$(echo "$output" | awk '/OVERALL TOTAL/ { print $NF }' | tail -n1)"
echo "monthly_cost=$monthly_cost"
echo "::set-output name=monthly_cost::$monthly_cost"
