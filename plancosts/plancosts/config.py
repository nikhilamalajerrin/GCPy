# plancosts/config/config.py
from __future__ import annotations
import os
import logging

try:
    from dotenv import load_dotenv  # pip install python-dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

log = logging.getLogger(__name__)

def _safe_load_env(path: str) -> None:
    """Load a dotenv file if it exists; never raise if it doesn't."""
    if not load_dotenv:
        return
    if os.path.isfile(path):
        try:
            # Keep existing env values; only fill missing ones
            load_dotenv(path, override=False)
        except Exception as e:  # mirror Go code’s “log.Fatal” semantics with a warning
            log.warning("Failed to load %s: %s", path, e)

# Load .env.local then .env (if they exist)
_safe_load_env(".env.local")
_safe_load_env(".env")

# Public config values (with sane defaults)
PRICE_LIST_API_ENDPOINT = os.getenv(
    "PLAN_COSTS_PRICE_LIST_API_ENDPOINT",
    "http://localhost:4000/graphql",
)
