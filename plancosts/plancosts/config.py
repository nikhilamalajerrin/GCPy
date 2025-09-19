from __future__ import annotations
import os

def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")

def _to_graphql_endpoint(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"

# Base URL (may be with or without /graphql)
API_URL = _rstrip_slash(os.getenv("PLANCOSTS_API_URL", "http://localhost:4000"))

# Old env var (keep supporting it); may be with or without /graphql
_LEGACY_ENDPOINT = os.getenv("PLAN_COSTS_PRICE_LIST_API_ENDPOINT", "").strip()

def resolve_endpoint(override: str | None = None) -> str:
    """
    Returns a fully-qualified GraphQL endpoint:
      - If --api-url/override is provided, normalize that.
      - Else if legacy env is set, normalize that.
      - Else normalize API_URL.
    """
    if override:
        return _to_graphql_endpoint(override)
    if _LEGACY_ENDPOINT:
        return _to_graphql_endpoint(_LEGACY_ENDPOINT)
    return _to_graphql_endpoint(API_URL)

# Back-compat constant (used by older imports)
PRICE_LIST_API_ENDPOINT = resolve_endpoint()
