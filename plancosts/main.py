#!/usr/bin/env python3
"""
Main entry point for plancosts - Generate cost reports from Terraform plans.
"""
import sys
import click
import json
from plancosts.parsers.terraform import parse_plan_file
from plancosts.base.costs import get_cost_breakdowns
from plancosts.outputs.json_output import to_json


@click.command()
@click.option(
    '--plan', '-p',
    required=True,
    type=click.Path(exists=True),
    help='Path to Terraform Plan JSON'
)
def main(plan):
    """Generate cost reports from Terraform plans"""
    try:
        # Parse the Terraform plan file
        resources = parse_plan_file(plan)
        
        if not resources:
            print("No supported resources found in plan file", file=sys.stderr)
            sys.exit(0)
        
        # Get cost breakdowns for all resources
        resource_cost_breakdowns = get_cost_breakdowns(resources)
        
        # Convert to JSON format and print
        json_output = to_json(resource_cost_breakdowns)
        print(json_output)
        
    except FileNotFoundError as e:
        print(f"Error: Plan file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in plan file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()