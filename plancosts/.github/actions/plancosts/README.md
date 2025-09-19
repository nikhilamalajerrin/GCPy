# plancosts GitHub Action

Runs your `plancosts` CLI and outputs:
- the table result (saved as `<prefix>-plancosts.txt`)
- the `monthly_cost` output (parsed from the “OVERALL TOTAL” line)

## Inputs
- `file_prefix` (required): Prefix for the output files (e.g. `master`, `pull_request`).

## Environment variables
- `TERRAFORM_DIR` (required if not using `TFPLAN_JSON`): Path to the Terraform project in the repo.
- `TFPLAN_JSON` (optional): Path to a pre-generated `terraform show -json` output file.
- `PLANCOSTS_API_URL` (optional): Pricing API base URL (your CLI already supports it).

## Outputs
- `monthly_cost`: Parsed monthly total.

## Example
See the workflow example in `.github/workflows/plancosts-diff.yml`.
