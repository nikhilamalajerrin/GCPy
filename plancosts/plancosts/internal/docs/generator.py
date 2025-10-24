from __future__ import annotations
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

# Import the Python resource registry dictionary
from plancosts.providers.terraform.aws.resource_registry import ResourceRegistry


def generate_supported_resources_docs(docs_templates_path: str, output_path: str) -> None:
    """
    Render supported_resources.md using Jinja2 and the current Terraform resource registry.
    Compatible replacement for Go's infracost-docs-generator.
    """
    env = Environment(loader=FileSystemLoader(docs_templates_path))
    tmpl = env.get_template("supported_resources.md")

    os.makedirs(output_path, exist_ok=True)
    output_file = Path(output_path) / "supported_resources.md"

    # Use the actual ResourceRegistry dict
    resource_registry_map = {
        name: {
            "aliases": getattr(item, "aliases", []),
            "notes": getattr(item, "notes", []),
        }
        for name, item in sorted(ResourceRegistry.items())
    }

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tmpl.render(resource_registry_map=resource_registry_map))


def generate_docs(docs_templates_path: str, output_path: str) -> None:
    """
    Entry point equivalent to Go's GenerateDocs.
    Creates output directory and generates supported_resources.md.
    """
    os.makedirs(output_path, exist_ok=True)
    generate_supported_resources_docs(docs_templates_path, output_path)
