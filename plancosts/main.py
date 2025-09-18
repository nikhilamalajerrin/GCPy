#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.
"""

from __future__ import annotations

import sys
import json
import click

from plancosts.parsers.terraform import parse_plan_file
from plancosts.base.costs import get_cost_breakdowns
from plancosts.output.json import to_json
from plancosts.output.table import to_table  # NEW


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--plan", "-p",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON (from `terraform show -json`)",
)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format",
)
def main(plan: str, output: str) -> None:
    """Generate cost reports from Terraform plans."""
    try:
        resources = parse_plan_file(plan)
        if not resources:
            click.echo("No supported resources found in plan file.", err=True)
            sys.exit(0)

        breakdowns = get_cost_breakdowns(resources)

        if output.lower() == "json":
            click.echo(to_json(breakdowns))
        else:
            click.echo(to_table(breakdowns))

    except FileNotFoundError as e:
        click.echo(f"Error: Plan file not found: {e}", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in plan file: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
