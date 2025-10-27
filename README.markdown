# GCPy 

Lightweight Python-based cost estimation for Terraform plans. This tool provides a CLI to estimate costs from Terraform plan JSON files or directories, using a mock pricing API for local development and CI..

## Table of Contents
- [Features](#features)
- [Quick Start](#quick-start)
- [Repository Layout](#repository-layout)
- [CLI Usage](#cli-usage)
- [Configuration](#configuration)
- [Mock Pricing API](#mock-pricing-api)
- [Development](#development)
- [GitHub Actions](#github-actions)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [FAQ](#faq)

## Features
- **CLI Tool**: Estimate costs from Terraform plan JSON or directories.
- **Mock Pricing API**: Run locally or in CI without external dependencies.
- **GitHub Actions**:
  - Python CI: Linting, type checking, tests, and CLI smoke tests.
  - PR Cost Diff: Comments cost differences on pull requests.
- **Sample Terraform Projects**: Examples under `examples/` for testing.

![image](https://i.imgur.com/MO3dUsB.png)

## Quick Start
Clone and set up the project:

```bash
git clone https://github.com/<your-username>/GCPy.git
cd GCPy
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" || pip install -r requirements.txt
```

Run against a test plan with the mock API:

```bash
export PLANCOSTS_API_URL=http://127.0.0.1:4000
python -m plancosts.tests.mock_price &  # Start mock API
python plancosts/main.py --tfjson plancosts/test_plan_ern.json -o table
```

## Repository Layout
```
.
├── .github/workflows/           # GitHub Actions
│   ├── python.yml              # Python CI: lint, typecheck, tests
│   └── plancosts-diff.yml      # PR cost diff comment
├── examples/terraform_0_13/    # Sample Terraform project
│   ├── main.tf
│   ├── storage/main.tf
│   ├── web_app/main.tf
│   └── plan.json
├── plancosts/                  # Python package
│   ├── main.py                 # CLI entry point
│   ├── config.py               # API endpoint/env handling
│   ├── base/ output/ parsers/ providers/  # Core logic
│   └── tests/                  # Tests and mock API
│       ├── mock_price.py       # Mock pricing API (POST /graphql)
│       ├── test_*.py
│       └── test_plan.json
├── Makefile                    # Dev helpers: fmt, lint, test
├── pyproject.toml              # Package metadata + extras
└── requirements.txt            # Fallback dependencies
```

## CLI Usage
Run the CLI from the repo root after installing dependencies:

```bash
python plancosts/main.py --tfjson <plan.json> -o table
python plancosts/main.py --tfdir examples/terraform_0_13 -o table
```

### Options
- `--tfjson PATH`: Path to a Terraform plan JSON file.
- `--tfdir DIR`: Directory of Terraform files (auto-derives resources).
- `-o table|json`: Output format (table or JSON).

## Configuration
The CLI uses a GraphQL endpoint for pricing data, configured via environment variables (in precedence order):

- `PLAN_COSTS_PRICE_LIST_API_ENDPOINT`: Legacy, accepts base URL or `/graphql`.
- `PLANCOSTS_API_URL`: Base URL (no `/graphql` needed).

Default: `http://127.0.0.1:4000`. The tool appends `/graphql` if needed.

Example:
```bash
export PLANCOSTS_API_URL=http://127.0.0.1:4000
```

## Mock Pricing API
A minimal GraphQL server is included for local and CI use:

```bash
python -m plancosts.tests.mock_price &  # Start in background
curl -X POST http://127.0.0.1:4000/graphql -d '{}' -H 'Content-Type: application/json'
```

**Note**: Only `POST /graphql` is supported; `GET /` returns 501.

## Development
Install dev tools and run checks:

```bash
make deps        # Install dev dependencies
make fmt         # Format code (Black, isort)
make lint        # Lint with Ruff
make typecheck   # Type check with MyPy
make test        # Run pytest
make check       # Run all checks
```

## GitHub Actions
### 1. Python CI (`.github/workflows/python.yml`)
- Runs on Python 3.10, 3.11, 3.12.
- Installs dependencies (`pyproject.toml` or `requirements.txt`).
- Runs Black, isort, Ruff, MyPy (non-blocking), and pytest.
- Starts mock API and performs CLI smoke tests with `test_plan*.json`.
- Key env: `PLANCOSTS_API_URL=http://127.0.0.1:4000`.

### 2. PR Cost Diff (`.github/workflows/plancosts-diff.yml`)
- Triggers on PRs modifying Terraform files, package, or workflow.
- Checks out base and PR branches to `base/` and `pr/`.
- Runs CLI on both branches (`--tfdir examples/terraform_0_13` or fallback JSON).
- Posts a PR comment with cost differences.
- Uses `POST /graphql` for mock API readiness.

## Troubleshooting
- **ModuleNotFoundError: plancosts.***: Ensure `PYTHONPATH` includes repo root or use `pip install -e .`.
- **CI can't open `pr/main.py`**: Verify checkout paths; keep `main.py` at repo root.
- **Mock server readiness fails**: Use `POST /graphql` for health checks (`GET /` returns 501).
- **Totals are 0.00**: Mock API uses placeholder prices. Use a real backend for accurate costs.

## Contributing
1. Create a feature branch from `main`.
2. Run `make check` locally.
3. Open a PR; workflows run automatically.
4. Update `examples/` or `tests/` if modifying parsers/providers.

## License
MIT. See `LICENSE` file if present.

## FAQ
**Why not use a custom GitHub Action?**  
Python-based workflows are simpler to maintain and debug without Docker.

**Can I make MyPy block CI?**  
Edit `python.yml` to remove `|| true` from the MyPy step.

**Can I change the Terraform examples path?**  
Update `TERRAFORM_DIR` in `plancosts-diff.yml` and related docs/scripts.
