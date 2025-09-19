#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.

Matches the Go CLI UX from commit 36a4950:
- Supports --tfplan-json OR (--tfplan with --tfdir) OR just --tfdir
- Prints validation errors in bright red
- Uses a GraphQL QueryRunner, endpoint from --api-url or env (PLANCOSTS_API_URL), falling back to config default
- Defaults to table output; supports --output json
"""
from __future__ import annotations

import os
import sys
import json
import logging
import click

# Optional: load .env / .env.local; safe even if files are missing.
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv(".env.local")
    load_dotenv()
except Exception:
    pass

from plancosts.parsers.terraform import (
    load_plan_json,
    generate_plan_json,
    parse_plan_json,
)
from plancosts.base.costs import get_cost_breakdowns
from plancosts.base.query import GraphQLQueryRunner
from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.output.json import to_json
from plancosts.output.table import to_table


def _fail(msg: str, ctx: click.Context | None = None) -> None:
    """Print a bright red error then exit; optionally show help."""
    click.secho(msg, fg="bright_red", err=True)
    if ctx is not None:
        click.echo(ctx.get_help(), err=True)
    raise SystemExit(1)


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--tfplan-json",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON file (from `terraform show -json`).",
)
@click.option(
    "--tfplan",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform Plan file. Requires --tfdir.",
)
@click.option(
    "--tfdir",
    type=click.Path(exists=False, file_okay=False, readable=True),
    help="Path to the Terraform project directory.",
)
@click.option(
    "--api-url",
    type=str,
    help="Price List API base URL (e.g., http://localhost:4000). Overrides PLANCOSTS_API_URL.",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Verbose logging.",
)
def main(
    tfplan_json: str | None,
    tfplan: str | None,
    tfdir: str | None,
    api_url: str | None,
    output: str,
    verbose: bool,
) -> None:
    """Generate cost reports from Terraform plans."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    ctx = click.get_current_context()

    # Validation (mirror Go CLI messages)
    if tfplan_json and tfplan:
        _fail(
            "Please only provide one of either a Terraform Plan JSON file (--tfplan-json) or a Terraform Plan file (--tfplan).",
            ctx,
        )

    if tfplan and not tfdir:
        _fail(
            "Please provide a path to the Terrafrom project (--tfdir) if providing a Terraform Plan file (--tfplan)\n",
            ctx,
        )

    if not tfplan_json and not tfdir:
        _fail(
            "Please provide either the path to the Terrafrom project (--tfdir) or a Terraform Plan JSON file (--tfplan-json).",
            ctx,
        )

    # Existence checks (so errors are ours and red)
    if tfplan_json and not os.path.isfile(tfplan_json):
        _fail(f"File not found: --tfplan-json '{tfplan_json}'")

    if tfplan and not os.path.isfile(tfplan):
        _fail(f"File not found: --tfplan '{tfplan}'")

    if tfdir and not os.path.isdir(tfdir):
        _fail(f"Directory not found: --tfdir '{tfdir}'")

    try:
        # Get plan JSON
        if tfplan_json:
            plan_json = load_plan_json(tfplan_json)
        else:
            # Either: (tfdir only) OR (tfplan + tfdir)
            plan_json = generate_plan_json(tfdir, tfplan)

        # Parse resources
        resources = parse_plan_json(plan_json)
        if not resources:
            click.echo("No supported resources found in plan.", err=True)
            sys.exit(0)

        # Build endpoint: --api-url overrides env/config; append /graphql like the Go code
        endpoint = f"{api_url.rstrip('/')}/graphql" if api_url else PRICE_LIST_API_ENDPOINT
        runner = GraphQLQueryRunner(endpoint)

        # Compute cost breakdowns (runner + resources)
        breakdowns = get_cost_breakdowns(runner, resources)

        # Render output
        if output.lower() == "json":
            click.echo(to_json(breakdowns))
        else:
            click.echo(to_table(breakdowns))

    except FileNotFoundError as e:
        _fail(f"Error: File not found: {e}")
    except json.JSONDecodeError as e:
        _fail(f"Error: Invalid JSON: {e}")
    except Exception as e:
        _fail(f"Error: {e}")


if __name__ == "__main__":
    main()
