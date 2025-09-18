# plancosts – Terraform Plan Cost Reporter

Generate hourly and monthly cost breakdowns from a Terraform plan. Supports output as a table (default) or JSON.

## Requirements

- **Python**: 3.9+ (recommended 3.10+)
- **Pricing API**: A running pricing API (defaults to `http://127.0.0.1:4000/`)
- **Terraform**: Required only if running against a project directory

## Install

1. (Optional but recommended) Create and activate a virtual environment:

   **macOS/Linux**:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell)**:
   ```
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

   If you don’t have a `requirements.txt`, install the required libraries: `click`, `decimal` (included in stdlib), and any other dependencies used by your modules.

## Environment

The CLI queries prices by POSTing GraphQL-like requests to an API.

- **PLANCOSTS_API_URL**: Base URL of the pricing API
  - Default: `http://127.0.0.1:4000/`
  - Example (macOS/Linux):
    ```
    export PLANCOSTS_API_URL=http://127.0.0.1:4000/
    ```

## Running

Run `plancosts` in one of two ways:

1. **From a Terraform plan JSON file** (output of `terraform show -json`):
   ```
   python main.py --tfplan-json path/to/plan.json -o table
   python main.py --tfplan-json path/to/plan.json -o json
   ```

2. **Directly from a Terraform project directory**:
   - If only `--tfpath` is provided, the tool runs `terraform init`, creates a temporary plan, and then `terraform show -json`.
   - If you have a binary plan file, provide `--tfplan` along with `--tfpath`.

   Examples:
   ```
   # Auto-create a plan from the project, then render table
   python main.py --tfpath /path/to/project -o table

   # Use an existing binary .tfplan file (requires tfpath)
   python main.py --tfpath /path/to/project --tfplan /path/to/file.tfplan -o json
   ```

## Options

- `--tfplan-json`: Path to a Terraform plan JSON file
- `--tfplan`: Path to a Terraform binary plan file (used with `--tfpath`)
- `--tfpath`: Path to the Terraform project directory
- `-o, --output`: Output format: `table` (default) or `json`
- `-v, --verbose`: Enable verbose logs (when supported by your build)

## Typical Workflow

1. (Optional) Produce a plan JSON:
   ```
   terraform -chdir=/path/to/project plan -out=tfplan.bin
   terraform -chdir=/path/to/project show -json tfplan.bin > plan.json
   ```

2. Run `plancosts`:
   ```
   python main.py --tfplan-json plan.json -o table
   ```

## Test Data

A minimal `test_plan.json` is provided to verify the pipeline, including:
- EC2 instance (with two EBS block devices)
- Standalone EBS volume
- (Optional, if added) EBS snapshot, snapshot copy, or ASG examples

## Troubleshooting

- **"No such option: --plan"**  
  The CLI uses `--tfplan-json` or `--tfpath/--tfplan`. Update your command.

- **Invalid directory for `--tfpath`**  
  Ensure `--tfpath` points to a valid Terraform project directory (containing `main.tf`).

- **Connection errors to pricing API**  
  Verify `PLANCOSTS_API_URL` is correct and the API (mock or real) is running at `http://127.0.0.1:4000/` (default).

- **Zero prices**  
  Indicates the API didn’t return a match for your filter (e.g., region, instance type, volume type). Check resource attributes or mock server data.

- **Module imports**  
  If Python can’t find modules like `plancosts.providers.terraform.aws.*`, verify your package layout and `PYTHONPATH`. Alternatively, install the package in editable mode:
   ```
   pip install -e .
   ```

## Development Notes

- The parser builds typed AWS Terraform resources (e.g., EC2, EBS, Launch Template/Config, ASG).
- Each resource has price components (e.g., instance hours, GB-month, IOPS-month).
- Pricing queries are batched and sent once per run.
- Output is rendered as a pretty table or JSON. The table shows a tree of resources with sub-resources (e.g., block devices).

## License

See the original project’s license if based on upstream. Otherwise, add your preferred license here.