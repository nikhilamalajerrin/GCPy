from __future__ import annotations

import os
from dataclasses import dataclass

# ---------- Helpers ----------

def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")

def _to_graphql_endpoint(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"


# Default base URL expected by tests
_DEFAULT_API = "http://localhost:4000"

@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str
    no_color: bool = False
    terraform_binary: str = "terraform"


def resolve_endpoint(override: str | None = None) -> str:
    """
    Build a fully-qualified GraphQL endpoint each time it's called.

    Precedence:
      1) explicit override (e.g., --api-url)
      2) legacy env PLAN_COSTS_PRICE_LIST_API_ENDPOINT
      3) primary env PLANCOSTS_API_URL
      4) default http://localhost:4000/
    """
    if override:
        base = override
    else:
        legacy = os.getenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "").strip()
        if legacy:
            base = legacy
        else:
            base = os.getenv("PLANCOSTS_API_URL", _DEFAULT_API)
    return _to_graphql_endpoint(base)


def load_config(api_url: str | None = None, no_color: bool = False) -> Config:
    return Config(
        price_list_api_endpoint=resolve_endpoint(api_url),
        no_color=no_color,
        terraform_binary=os.getenv("TERRAFORM_BINARY", "terraform"),
    )

# Back-compat constant for older imports; computed from current env at import time.
PRICE_LIST_API_ENDPOINT = resolve_endpoint()
