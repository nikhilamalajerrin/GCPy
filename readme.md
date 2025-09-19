# GCPy – Terraform Plan Cost Reporter

Generate hourly and monthly cost breakdowns from a Terraform plan. Supports output as a table (default) or JSON. Currently focused on AWS Terraform resources; GCP/Terragrunt naming carried over from earlier prototypes. Aimed mainly for GCPy and Terragrunt, with AWS support in v1.

## Requirements

- **Python**: 3.9+ (recommended 3.10+)
- **Pricing API**: A running pricing API (defaults to `http://127.0.0.1:4000/`)
- **Terraform**: Only required if running against a project directory (`--tfdir`)

## Install

1. (Optional but recommended) Create and activate a virtual environment:

   **macOS/Linux**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell)**:
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   Or minimally:
   ```bash
   pip install click
   ```

   For local development, install in editable mode:
   ```bash
   pip install -e .
   ```

## Environment

The CLI queries prices by POSTing GraphQL-like requests to an API.

- **PLANCOSTS_API_URL**: Base URL for the pricing API (normalized to `/graphql` internally).
  - Default: `http://127.0.0.1:4000/`
  - Example:
    ```bash
    export PLANCOSTS_API_URL=http://127.0.0.1:4000/
    ```

  Back-compat: `PLAN_COSTS_PRICE_LIST_API_ENDPOINT` is also read if present (exported as `PRICE_LIST_API_ENDPOINT`).

- **TERRAFORM_BINARY**: Override the `terraform` executable path (used with `--tfdir` or `--tfplan`).
  - Example:
    ```bash
    export TERRAFORM_BINARY=~/bin/terraform_0.13
    ```

## Running

Run the CLI in one of three modes:

1. **From a Terraform plan JSON file** (output of `terraform show -json`):
   ```bash
   python main.py --tfjson path/to/plan.json -o table
   python main.py --tfjson path/to/plan.json -o json
   ```

2. **From a Terraform project directory** (auto-runs `terraform init`, generates a temp plan, and `terraform show -json`):
   ```bash
   python main.py --tfdir /path/to/project -o table
   ```

3. **From a Terraform project directory + existing binary plan**:
   ```bash
   python main.py --tfdir /path/to/project --tfplan /path/to/plan.tfplan -o json
   ```

## CLI Options

- `--tfjson PATH`: Path to a Terraform plan JSON file.
- `--tfdir DIR`: Path to a Terraform project directory.
- `--tfplan PATH`: Path to a Terraform binary plan (use with `--tfdir`).
- `-o, --output {table,json}`: Output format (default: `table`).
- `--api-url URL`: Override pricing API endpoint (also via `PLANCOSTS_API_URL`).
- `-v, --verbose`: Enable verbose logging.

**Note**: Use `--tfjson` instead of legacy `--tfplan-json`. Use `--tfdir` instead of `--tfpath`.

## Typical Workflow

1. (Optional) Produce a plan JSON:
   ```bash
   terraform -chdir=/path/to/project plan -out=tfplan.bin
   terraform -chdir=/path/to/project show -json tfplan.bin > plan.json
   ```

2. Run the tool:
   ```bash
   python main.py --tfjson plan.json -o table
   ```

## Features Implemented

### AWS Resources Supported

- `aws_instance` (EC2)
- `aws_ebs_volume`
- `aws_ebs_snapshot`
- `aws_ebs_snapshot_copy`
- `aws_launch_configuration`
- `aws_launch_template`
- `aws_autoscaling_group`
- Classic ELB: `aws_elb`
- ALB/NLB: `aws_lb` / `aws_alb`
- `aws_nat_gateway`
- RDS instance: `aws_db_instance`

### Module Support

- Recursively parses `planned_values.root_module.child_modules[*]`.
- Matches child module configs under `configuration.root_module.module_calls.<name>.module`.
- Emits module-qualified addresses (e.g., `module.storage[0].aws_ebs_volume.standard`) to avoid collisions.
- Wires references inside modules (e.g., module snapshot → module volume).

### Region Resolution

- Uses provider region from `configuration.provider_config.aws.expressions.region.constant_value` when set.
- Overrides from any `values.arn` (parses ARN region token).
- Fallback: `us-east-1`.

### EC2/EBS Nuances

- Tenancy normalization (Infracost parity): `dedicated` → `Dedicated`; else → `Shared`.
- Defaults to 8 GB root volume if block device size unspecified.
- Safe handling of instances/LT/LC with no additional volumes.
- Legacy LC shapes: `block_device_mappings[].ebs[0]`.

### Snapshot Pricing Filters

- Uses REGEX for `usagetype` (e.g., `EBS:SnapshotUsage`) to match correctly and avoid multi-price collisions.

### Pricing API Batching

- GraphQL-style batch requests; unpacks responses to per-resource, per-price-component entries.
- Handles missing/none/multiple prices gracefully (missing → cost 0).

## Mock Pricing API

A lightweight mock server is included: `mock_pricing_api.py`.

Start it:
```bash
export PLANCOSTS_API_URL=http://127.0.0.1:4000
python mock_pricing_api.py
```

### Environment Switches

- `MOCK_MODE`: `normal` | `multiple` | `none` | `error`

### Base/Override Prices

- `MOCK_BASE_PRICE` (default base)
- `MOCK_PRICE_EC2`
- `MOCK_PRICE_EBS_GB`
- `MOCK_PRICE_EBS_IOPS`
- `MOCK_PRICE_SNAPSHOT_GB`
- `MOCK_PRICE_ELB_CLASSIC`
- `MOCK_PRICE_ELB_ALB`
- `MOCK_PRICE_ELB_NLB`
- `MOCK_PRICE_NATGW_HR`
- `MOCK_PRICE_RDS_INSTANCE_HR`
- `MOCK_PRICE_RDS_STORAGE_GB`
- `MOCK_PRICE_RDS_IOPS`

## Test Data / Quick Checks

- **Comprehensive plan**: `test_plan_ern.json`  
  Covers EC2 + EBS + Snapshots + Snapshot Copy + LC/ASG + ELB/ALB/NLB + NATGW + RDS (with ARN-based region override).

- **Modules plan**: `test_modules.json`  
  Demonstrates child modules and module-internal references.

Run:
```bash
# Start mock (in one shell)
export PLANCOSTS_API_URL=http://127.0.0.1:4000
python mock_pricing_api.py

# Then (in another shell)
python main.py --tfjson test_plan_ern.json -o table
python main.py --tfjson test_modules.json -o table
```

## Troubleshooting

- **Zero prices**  
  Filters didn’t match (e.g., region, instance type, storage type, IOPS). Check attributes or adjust mock overrides.

- **"terraform not found" with `--tfdir`/`--tfplan`**  
  Set `TERRAFORM_BINARY` or install Terraform.

- **Modules not appearing**  
  Ensure plan JSON has `planned_values.root_module.child_modules[*]` and matching `configuration.root_module.module_calls`.

- **"No such option: --plan"`**  
  Use `--tfjson` or `--tfdir`/`--tfplan`. Update your command.

- **Invalid directory for `--tfdir`**  
  Ensure it contains a valid Terraform project (e.g., `main.tf`).

- **Connection errors to pricing API**  
  Verify `PLANCOSTS_API_URL` and that the API (mock or real) is running.

- **Module imports fail** (e.g., `plancosts.providers.terraform.aws.*`)  
  Verify package layout/`PYTHONPATH`, or run `pip install -e .`.

## Development Notes

- Parser → typed resources → batched price queries → pretty table or JSON output.
- Base classes: region filters, default filters, value mappings (incl. tenancy normalization).
- Snapshots: filtered REGEX `usagetype` matching.
- No background work: each run loads/generates plan, queries prices, prints result.
- The parser builds typed AWS resources (e.g., EC2, EBS, Launch Template/Config, ASG).
- Each resource has price components (e.g., instance hours, GB-month, IOPS-month).
- Pricing queries batched once per run.
- Output: tree of resources with sub-resources (e.g., block devices).

## License

MIT License