#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.

This version matches the Go CLI UX:
- Supports --tfplan-json OR (--tfplan with --tfpath) OR just --tfpath
- Prints argument/validation errors in bright red (like color.HiRed in Go)
- Defaults to table output; supports --output json
"""

from __future__ import annotations

import os
import sys
import json
import logging
import click

# Optional: load .env / .env.local like the Go version
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
    # We validate existence ourselves so we can print red errors.
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON file (from `terraform show -json`).",
)
@click.option(
    "--tfplan",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform binary plan file (requires --tfpath).",
)
@click.option(
    "--tfpath",
    type=click.Path(exists=False, file_okay=False, readable=True),
    help=(
        "Path to the Terraform project directory. "
        "If provided without --tfplan, runs `terraform init/plan/show -json` to generate the plan JSON."
    ),
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
    tfpath: str | None,
    output: str,
    verbose: bool,
) -> None:
    """Generate cost reports from Terraform plans."""
    # Logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    ctx = click.get_current_context()

    # Argument validation (mirror Go CLI messages, but red)
    if tfplan_json and tfplan:
        _fail(
            "Please only provide one of either a Terraform Plan JSON file (--tfplan-json) or a Terraform Plan file (--tfplan).",
            ctx,
        )

    if tfplan and not tfpath:
        _fail(
            "Please provide a path to the Terraform project (--tfpath) if providing a Terraform Plan file (--tfplan).\n",
            ctx,
        )

    if not tfplan_json and not tfpath:
        _fail(
            "Please provide either the path to the Terraform project (--tfpath) or a Terraform Plan JSON file (--tfplan-json).",
            ctx,
        )

    # Existence checks so errors are ours (and red), not Click's
    if tfplan_json and not os.path.isfile(tfplan_json):
        _fail(f"File not found: --tfplan-json '{tfplan_json}'")

    if tfplan and not os.path.isfile(tfplan):
        _fail(f"File not found: --tfplan '{tfplan}'")

    if tfpath and not os.path.isdir(tfpath):
        _fail(f"Directory not found: --tfpath '{tfpath}'")

    try:
        # Acquire plan JSON
        if tfplan_json:
            plan_json = load_plan_json(tfplan_json)
        else:
            # Either: (tfpath only) OR (tfplan + tfpath)
            plan_json = generate_plan_json(tfpath, tfplan)

        # Parse resources
        resources = parse_plan_json(plan_json)
        if not resources:
            click.echo("No supported resources found in plan.", err=True)
            sys.exit(0)

        # Compute cost breakdowns
        breakdowns = get_cost_breakdowns(resources)

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
