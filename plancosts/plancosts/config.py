"""
Lightweight config loader (dotenv optional).

Mirrors the Go change that made loading .env/.env.local safe if files
don’t exist. Exposes PRICE_LIST_API_ENDPOINT for the query runner.
"""
from __future__ import annotations

import os
from pathlib import Path

def _safe_load_dotenv(path: str) -> None:
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            from dotenv import load_dotenv  # optional dependency
            load_dotenv(p)
    except Exception:
        # Don’t crash if dotenv isn’t installed or loading fails.
        pass

# Load .env.local then .env if present (no errors if missing)
_safe_load_dotenv(".env.local")
_safe_load_dotenv(".env")

# Public config values
PRICE_LIST_API_ENDPOINT: str = os.getenv(
    "PLAN_COSTS_PRICE_LIST_API_ENDPOINT",
    "http://127.0.0.1:4000/graphql",
)
