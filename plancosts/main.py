#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.

Renamed flag: --tfplan-json -> --tfjson (keeps --tfplan-json as an alias).

Matches the Go CLI UX:
- Supports --tfjson OR (--tfplan with --tfdir) OR just --tfdir
- Prints validation errors in bright red
- Uses a GraphQL QueryRunner, endpoint from --api-url or env (PLANCOSTS_API_URL)
- Defaults to table output; supports --output json
- NEW: --no-color (turn off colored output; our renderer is ASCII-only so this
       simply guarantees no ANSI escapes appear if future formatting is added)
"""
from __future__ import annotations

import json
import logging
import os
import sys

import click

# Optional: load .env / .env.local
try:
    from dotenv import load_dotenv  # pip install python-dotenv

    load_dotenv(".env.local")
    load_dotenv()
except Exception:
    pass

from plancosts.base.costs import get_cost_breakdowns
from plancosts.base.query import GraphQLQueryRunner
from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.output.json import to_json
from plancosts.output.table import to_table
from plancosts.parsers.terraform import (
    generate_plan_json,
    load_plan_json,
    parse_plan_json,
)


def _fail(msg: str, ctx: click.Context | None = None) -> None:
    click.secho(msg, fg="bright_red", err=True)
    if ctx is not None:
        click.echo(ctx.get_help(), err=True)
    raise SystemExit(1)


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--tfjson",
    "--tfplan-json",  # deprecated alias kept for back-compat
    "tfjson",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON file (from `terraform show -json`). (alias: --tfplan-json)",
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
@click.option(
    "--no-color",
    is_flag=True,
    help="Turn off colored output.",
)
def main(
    tfjson: str | None,
    tfplan: str | None,
    tfdir: str | None,
    api_url: str | None,
    output: str,
    verbose: bool,
    no_color: bool,
) -> None:
    """Generate cost reports from Terraform plans."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    ctx = click.get_current_context()

    # Validation (match Go messages)
    if tfjson and tfplan:
        _fail(
            "Please only provide one of either a Terraform Plan JSON file (tfjson) or a Terraform Plan file (tfplan)",
            ctx,
        )

    if tfplan and not tfdir:
        _fail(
            "Please provide a path to the Terrafrom project (tfdir) if providing a Terraform Plan file (tfplan)\n",
            ctx,
        )

    if not tfjson and not tfdir:
        _fail(
            "Please provide either the path to the Terrafrom project (tfdir) or a Terraform Plan JSON file (tfjson).",
            ctx,
        )

    # Existence checks
    if tfjson and not os.path.isfile(tfjson):
        _fail(f"File not found: --tfjson '{tfjson}'")

    if tfplan and not os.path.isfile(tfplan):
        _fail(f"File not found: --tfplan '{tfplan}'")

    if tfdir and not os.path.isdir(tfdir):
        _fail(f"Directory not found: --tfdir '{tfdir}'")

    try:
        # Get plan JSON
        if tfjson:
            plan_json = load_plan_json(tfjson)
        else:
            # Either: (tfdir only) OR (tfplan + tfdir)
            plan_json = generate_plan_json(tfdir, tfplan)

        # Parse resources
        resources = parse_plan_json(plan_json)
        if not resources:
            click.echo("No supported resources found in plan.", err=True)
            sys.exit(0)

        # Build endpoint: --api-url overrides; ensure /graphql suffix
        endpoint = (
            f"{api_url.rstrip('/')}/graphql" if api_url else PRICE_LIST_API_ENDPOINT
        )
        runner = GraphQLQueryRunner(endpoint)

        # Compute cost breakdowns
        breakdowns = get_cost_breakdowns(runner, resources)

        # Render
        if output.lower() == "json":
            click.echo(to_json(breakdowns))
        else:
            click.echo(to_table(breakdowns, no_color=no_color))

    except FileNotFoundError as e:
        _fail(f"Error: File not found: {e}")
    except json.JSONDecodeError as e:
        _fail(f"Error: Invalid JSON: {e}")
    except Exception as e:
        _fail(f"Error: {e}")


if __name__ == "__main__":
    main()
