#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.
"""

from __future__ import annotations

import sys
import json
import click
import logging

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


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--tfplan-json",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON file (from `terraform show -json`).",
)
@click.option(
    "--tfplan",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to Terraform binary plan file (requires --tfpath).",
)
@click.option(
    "--tfpath",
    type=click.Path(exists=True, file_okay=False, readable=True),
    help="Path to the Terraform project directory. If provided without --tfplan, "
         "we run `terraform init/plan/show -json` to generate the plan JSON.",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Verbose logging",
)
def main(tfplan_json: str | None, tfplan: str | None, tfpath: str | None, output: str, verbose: bool) -> None:
    """Generate cost reports from Terraform plans."""
    # Logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Arg validation (mirror the Go UX)
    if tfplan_json and tfplan:
        click.echo("Please provide only one of --tfplan-json or --tfplan.", err=True)
        sys.exit(1)

    if not tfplan_json and not (tfplan or tfpath):
        click.echo("Provide either --tfplan-json OR (--tfplan with --tfpath) OR --tfpath.", err=True)
        sys.exit(1)

    if tfplan and not tfpath:
        click.echo("When using --tfplan, you must also provide --tfpath.", err=True)
        sys.exit(1)

    try:
        # Acquire plan JSON
        if tfplan_json:
            plan_json = load_plan_json(tfplan_json)
        else:
            # Either: (tfpath only) OR (tfplan + tfpath)
            plan_json = generate_plan_json(tfpath, tfplan)

        resources = parse_plan_json(plan_json)
        if not resources:
            click.echo("No supported resources found in plan.", err=True)
            sys.exit(0)

        breakdowns = get_cost_breakdowns(resources)

        if output.lower() == "json":
            click.echo(to_json(breakdowns))
        else:
            click.echo(to_table(breakdowns))

    except FileNotFoundError as e:
        click.echo(f"Error: File not found: {e}", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
