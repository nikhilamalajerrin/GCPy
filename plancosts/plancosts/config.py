from __future__ import annotations

import os
from dataclasses import dataclass

# ---------- Helpers ----------


def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")


def _to_graphql_endpoint(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"


# ---------- Defaults & envs ----------

# Default to local mock so dev works OOTB
_DEFAULT_API = "http://127.0.0.1:4000"

# Primary env (with or without /graphql)
_API_ENV = os.getenv("PLANCOSTS_API_URL", _DEFAULT_API)

# Legacy env (still supported)
_LEGACY_ENDPOINT = os.getenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "").strip()

# Optional: path to terraform binary (cc0ec5f parity)
_TERRAFORM_BINARY = os.getenv("TERRAFORM_BINARY") or "terraform"


@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str
    no_color: bool = False
    terraform_binary: str = "terraform"


def resolve_endpoint(override: str | None = None) -> str:
    """
    Returns a fully-qualified GraphQL endpoint:
      1) CLI override (if provided)
      2) Legacy env PLAN_COSTS_PRICE_LIST_API_ENDPOINT
      3) PLANCOSTS_API_URL (or default)
    """
    if override:
        return _to_graphql_endpoint(override)
    if _LEGACY_ENDPOINT:
        return _to_graphql_endpoint(_LEGACY_ENDPOINT)
    return _to_graphql_endpoint(_API_ENV)


def load_config(api_url: str | None = None, no_color: bool = False) -> Config:
    return Config(
        price_list_api_endpoint=resolve_endpoint(api_url),
        no_color=no_color,
        terraform_binary=_TERRAFORM_BINARY,
    )


# Back-compat constant for older imports
PRICE_LIST_API_ENDPOINT = resolve_endpoint()
