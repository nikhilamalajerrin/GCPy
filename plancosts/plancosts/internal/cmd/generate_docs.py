#!/usr/bin/env python3
"""
CLI for generating documentation from Jinja2 templates.
Equivalent to infracost-docs-generator in Go.
"""

import os
import argparse
import logging
from plancosts.internal.docs.generator import generate_docs


def getcwd() -> str:
    try:
        return os.getcwd()
    except Exception as e:
        logging.warning(f"Failed to get cwd: {e}")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="plancosts-generate-docs",
        description="Generate documentation files from templates.",
    )
    parser.add_argument(
        "--input", "-i", help="Path to docs templates directory", default=""
    )
    parser.add_argument(
        "--output", "-o", help="Path to docs output directory", default=""
    )
    parser.add_argument(
        "--log-level",
        "-l",
        help="Log level (TRACE, DEBUG, INFO, WARN, ERROR)",
        default="WARN",
    )

    args = parser.parse_args()

    level_map = {
        "TRACE": logging.DEBUG,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    logging.basicConfig(
        level=level_map.get(args.log_level.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )

    templates_path = args.input or os.path.join(getcwd(), "docs", "templates")
    output_path = args.output or os.path.join(getcwd(), "docs", "generated")

    os.makedirs(output_path, exist_ok=True)
    logging.info(f"Using template path: {templates_path}")
    logging.info(f"Output path: {output_path}")

    try:
        generate_docs(templates_path, output_path)
        logging.info("✅ Documentation generation completed successfully.")
    except Exception as e:
        logging.error(f"❌ Failed to generate docs: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
