# plancosts/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------- helpers ----------------

def _rstrip_slash(url: str) -> str:
    return (url or "").rstrip("/")


def _ensure_graphql_suffix(url: str) -> str:
    url = _rstrip_slash(url)
    return url if url.endswith("/graphql") else f"{url}/graphql"


def _repo_root() -> Path:
    """
    Mirror the Go rootDir() that climbs from this file's dir to repo root.
    Our layout is .../<repo>/plancosts/config.py → repo root = parents[1].
    """
    return Path(__file__).resolve().parents[1]


def _file_exists(p: Path) -> bool:
    try:
        return p.exists() and p.is_file()
    except Exception:
        return False


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    # Skip comments/empties; parse KEY=VALUE (no export support needed)
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "=" not in s:
        return None
    k, v = s.split("=", 1)
    return k.strip(), v.strip().strip('"').strip("'")  # simple quoting trim


def _load_env_file(path: Path) -> None:
    """
    Lightweight .env loader (no external deps). Overwrites existing env vars,
    which matches typical godotenv.Load behavior.
    """
    if not _file_exists(path):
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                kv = _parse_env_line(line)
                if kv is None:
                    continue
                k, v = kv
                os.environ[k] = v
    except Exception:
        # Fail-soft like the Go code (it would log.Fatal on error reading,
        # but soft-fail avoids blocking execution for dotfile quirks)
        pass


# ---------------- config model ----------------

@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str
    no_color: bool = False
    terraform_binary: str = "terraform"


def resolve_endpoint(override: str | None = None) -> str:
    """
    Build a fully-qualified GraphQL endpoint.

    Precedence (mirrors Go's INFRACOST_API_URL while keeping Python compat):
      1) explicit override
      2) INFRACOST_API_URL
      3) PLANCOSTS_API_URL          (older python name)
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
    # Load .env files like the Go version:
    # - .env.local from repo root
    # - .env from CWD
    _load_env_file(_repo_root() / ".env.local")
    _load_env_file(Path.cwd() / ".env")

    return Config(
        price_list_api_endpoint=resolve_endpoint(api_url),
        no_color=no_color or (os.getenv("NO_COLOR", "").lower() in ("1", "true", "yes")),
        terraform_binary=os.getenv("TERRAFORM_BINARY", "terraform"),
    )


# Global config & back-compat constant
CONFIG = load_config()
PRICE_LIST_API_ENDPOINT = CONFIG.price_list_api_endpoint
