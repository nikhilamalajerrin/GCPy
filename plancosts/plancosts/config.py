# plancosts/config.py
from __future__ import annotations

import os
from dataclasses import dataclass

# ---------- Helpers ----------

def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")

def _ensure_graphql_suffix(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"


@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str
    no_color: bool = False
    terraform_binary: str = "terraform"


def resolve_endpoint(override: str | None = None) -> str:
    """
    Build a fully-qualified GraphQL endpoint each time it's called.

    Precedence (mirrors Go's INFRACOST_API_URL while remaining back-compatible):
      1) explicit override (e.g. from --api-url)
      2) INFRACOST_API_URL (Go name)
      3) PLANCOSTS_API_URL   (Python name used earlier)
      4) PLAN_COSTS_PRICE_LIST_API_ENDPOINT (legacy)
      5) default https://pricing.infracost.io
    """
    if override:
        base = override
    else:
        base = (
            os.getenv("INFRACOST_API_URL")
            or os.getenv("PLANCOSTS_API_URL")
            or os.getenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT")
            or "https://pricing.infracost.io"
        )
    return _ensure_graphql_suffix(base)


def load_config(api_url: str | None = None, no_color: bool = False) -> Config:
    return Config(
        price_list_api_endpoint=resolve_endpoint(api_url),
        no_color=no_color,
        terraform_binary=os.getenv("TERRAFORM_BINARY", "terraform"),
    )

# Back-compat constant for older imports; computed from current env at import time.
PRICE_LIST_API_ENDPOINT = resolve_endpoint()
