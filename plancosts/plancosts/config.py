# plancosts/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------- tiny helpers ----------------

def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")

def _ensure_graphql_suffix(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"

def _repo_root() -> Path:
    # <repo>/plancosts/config.py → repo root = parents[1]
    return Path(__file__).resolve().parents[1]

def _file_exists(p: Path) -> bool:
    try:
        return p.exists() and p.is_file()
    except Exception:
        return False

def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    k, v = s.split("=", 1)
    return k.strip(), v.strip().strip('"').strip("'")

def _load_env_file(path: Path) -> None:
    # Fail-soft; overwrite existing env vars like godotenv.Load
    if not _file_exists(path):
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                kv = _parse_env_line(line)
                if kv:
                    os.environ[kv[0]] = kv[1]
    except Exception:
        pass

# ---------------- config model ----------------

@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str
    no_color: bool = False
    terraform_binary: str = "terraform"

_ENV_PRIORITY = (
    "INFRACOST_API_URL",                 # Go-compatible (default exists in Go)
    "PLANCOSTS_API_URL",                 # Python back-compat
    "PLAN_COSTS_PRICE_LIST_API_ENDPOINT" # legacy
)

def resolve_endpoint(override: str | None = None) -> str:
    """
    Build a fully-qualified GraphQL endpoint.

    Precedence:
      1) explicit override (CLI)
      2) INFRACOST_API_URL
      3) PLANCOSTS_API_URL
      4) PLAN_COSTS_PRICE_LIST_API_ENDPOINT
      5) default https://pricing.infracost.io
    """
    if override:
        base = override
    else:
        base = next((os.getenv(k) for k in _ENV_PRIORITY if os.getenv(k)), None) or "https://pricing.infracost.io"
    return _ensure_graphql_suffix(base)

def load_config(api_url: str | None = None, no_color: bool = False) -> Config:
    # Mimic Go's loader: repo .env.local then cwd .env
    _load_env_file(_repo_root() / ".env.local")
    _load_env_file(Path.cwd() / ".env")

    return Config(
        price_list_api_endpoint=resolve_endpoint(api_url),
        no_color=no_color or os.getenv("NO_COLOR", "").lower() in ("1", "true", "yes"),
        terraform_binary=os.getenv("TERRAFORM_BINARY", "terraform"),
    )

# Global config & stable constant for old imports
CONFIG = load_config()
PRICE_LIST_API_ENDPOINT = CONFIG.price_list_api_endpoint
