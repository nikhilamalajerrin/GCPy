#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.

Pipeline:
- parse plan -> provider resources
- price each resource in place (GraphQL)
- render table or JSON

Flags CLI:
  -o, --output         table|json (default: table)
  --log-level          TRACE|DEBUG|INFO|WARN|ERROR (default: WARN)
  -v, --verbose        convenience alias for DEBUG (ignored if --log-level set)
  --no-color           disable colored output (table renderers honor this)
  --tfjson | --tfplan + --tfdir
  --api-url            Price List API base URL (fallback: PRICE_LIST_API_ENDPOINT)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, List
from decimal import Decimal, InvalidOperation

import click

# Optional .env support
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv(".env.local")
    load_dotenv()
except Exception:
    pass

from plancosts.config import PRICE_LIST_API_ENDPOINT
from plancosts.providers.terraform import load_plan_json, generate_plan_json, parse_plan_json
from plancosts.prices.query import GraphQLQueryRunner
from plancosts.prices.prices import get_prices
from plancosts.output.json import to_json as output_to_json

# Try to use Rich renderer if installed
try:
    from plancosts.output.table_rich import render_table as render_table_rich
    _HAS_RICH_TABLE = True
except Exception:
    _HAS_RICH_TABLE = False

# Fallback ASCII renderer (optional)
try:
    from plancosts.output.table import to_table as render_table_ascii
except Exception:
    render_table_ascii = None

# Spinner (prefer Rich; fallback to plain stderr text)
try:
    from rich.console import Console as _RichConsole
    _HAS_RICH_SPINNER = True
except Exception:
    _HAS_RICH_SPINNER = False


# ---------------- helpers: duck-typing accessors ----------------
def _d(x) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _call_maybe(obj: Any, *names: str, default=None):
    for n in names:
        if hasattr(obj, n):
            attr = getattr(obj, n)
            if callable(attr):
                try:
                    return attr()
                except TypeError:
                    pass
            else:
                return attr
    return default


def _name_of_resource(r: Any) -> str:
    # Prefer name, fall back to address
    return (
        _call_maybe(r, "name", "Name")
        or _call_maybe(r, "address", "Address")
        or "<resource>"
    )


def _resource_sort_key(r: Any) -> tuple[int, str]:
    return (0, (_name_of_resource(r) or "").lower())


# ---------------- CLI ----------------
def _fail(msg: str, ctx: click.Context | None = None) -> None:
    click.secho(msg, fg="bright_red", err=True)
    if ctx is not None:
        click.echo(ctx.get_help(), err=True)
    raise SystemExit(1)


def _set_log_level(log_level: str | None, verbose: bool) -> None:
    """
    levels:
      TRACE -> logging.NOTSET (or DEBUG with extra verbosity)
      DEBUG -> logging.DEBUG
      INFO  -> logging.INFO
      WARN  -> logging.WARN
      ERROR -> logging.ERROR
    If --log-level not given, -v maps to DEBUG, else WARN by default.
    """
    mapping = {
        "TRACE": logging.DEBUG,   # Python lacks TRACE; map to DEBUG
        "DEBUG": logging.DEBUG,
        "INFO":  logging.INFO,
        "WARN":  logging.WARN,
        "ERROR": logging.ERROR,
    }
    if log_level:
        level = mapping.get(log_level.upper(), logging.WARN)
    else:
        level = logging.DEBUG if verbose else logging.WARN

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    if log_level and log_level.upper() == "TRACE":
        logging.getLogger().debug("TRACE enabled (mapped to DEBUG)")


def _price_with_spinner(resources: List[Any], runner: GraphQLQueryRunner, no_color: bool) -> None:
    """
    Price all resources, showing a spinner 'Add calculating costs spinner'.
    Uses Rich if available; falls back to plain stderr text otherwise.
    """
    total = len(resources)

    if _HAS_RICH_SPINNER:
        console = _RichConsole(no_color=no_color, stderr=True)
        # Use the Status object returned by console.status and call .update() on it
        with console.status("Calculating costs…", spinner="dots") as status:
            for i, r in enumerate(resources, start=1):
                name = _name_of_resource(r)
                status.update(f"Calculating costs… ({i}/{total}) {name}")
                get_prices(r, runner)
        return

    # Fallback (no Rich): simple stderr messages
    click.echo("Calculating costs…", err=True)
    for r in resources:
        get_prices(r, runner)
    click.echo("Calculating costs… done.", err=True)


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--tfjson",
    "--tfplan-json",
    "tfjson",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform plan JSON file (from `terraform show -json`).",
)
@click.option(
    "--tfplan",
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to Terraform plan file. Requires --tfdir.",
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
@click.option("--pretty", is_flag=True, help="Pretty-print JSON when -o json.")
@click.option("--log-level", type=click.Choice(["TRACE", "DEBUG", "INFO", "WARN", "ERROR"], case_sensitive=True), help="Log level.")
@click.option("-v", "--verbose", is_flag=True, help="Enable DEBUG logs (ignored if --log-level is set).")
@click.option("--no-color", is_flag=True, help="Turn off colored output.")
def main(
    tfjson: str | None,
    tfplan: str | None,
    tfdir: str | None,
    api_url: str | None,
    output: str,
    pretty: bool,
    log_level: str | None,
    verbose: bool,
    no_color: bool,
) -> None:
    """Generate cost reports from Terraform plans."""
    _set_log_level(log_level, verbose)
    ctx = click.get_current_context()

    # Validate arg combos behavior
    if tfjson and tfplan:
        _fail("Provide only one of --tfjson or --tfplan.", ctx)
    if tfplan and not tfdir:
        _fail("Please provide --tfdir when using --tfplan.", ctx)
    if not tfjson and not tfdir:
        _fail("Please provide either --tfjson or --tfdir (with optional --tfplan).", ctx)

    # Existence checks
    if tfjson and not os.path.isfile(tfjson):
        _fail(f"File not found: --tfjson '{tfjson}'")
    if tfplan and not os.path.isfile(tfplan):
        _fail(f"File not found: --tfplan '{tfplan}'")
    if tfdir and not os.path.isdir(tfdir):
        _fail(f"Directory not found: --tfdir '{tfdir}'")

    try:
        # Load plan JSON
        if tfjson:
            plan_json = load_plan_json(tfjson)
        else:
            plan_json = generate_plan_json(tfdir, tfplan)

        # Parse provider resources
        resources: List[Any] = parse_plan_json(plan_json)
        if not resources:
            click.echo("No supported resources found in plan.", err=True)
            sys.exit(0)

        # Build GraphQL endpoint: CLI override > env/Config default
        endpoint = f"{api_url.rstrip('/')}/graphql" if api_url else PRICE_LIST_API_ENDPOINT
        runner = GraphQLQueryRunner(endpoint)

        # Price each resource (with spinner)
        _price_with_spinner(resources, runner, no_color=no_color)

        # Output
        fmt = output.lower()
        if fmt == "table":
            if _HAS_RICH_TABLE:
                text = render_table_rich(resources, no_color=no_color)
                print(text, end="")
            else:
                if render_table_ascii is None:
                    raise RuntimeError("table renderer not available")
                print(render_table_ascii(resources))
        elif fmt == "json":
            resources_sorted = sorted(resources, key=_resource_sort_key)
            payload = output_to_json(resources_sorted, pretty=pretty)
            sys.stdout.buffer.write(payload)
            if pretty:
                sys.stdout.write("\n")
        else:
            _fail("Unknown output format.", ctx)

    except FileNotFoundError as e:
        _fail(f"Error: File not found: {e}")
    except json.JSONDecodeError as e:
        _fail(f"Error: Invalid JSON: {e}")
    except Exception as e:
        _fail(f"Error: {e}")


if __name__ == "__main__":
    main()
