# plancosts/config.py
from __future__ import annotations
import os
from dataclasses import dataclass

# Optional: load .env files if present
try:
    from dotenv import load_dotenv
    # load .env.local first (can override by .env)
    load_dotenv(".env.local", override=True)
    load_dotenv(override=False)
except Exception:
    # python-dotenv is optional; env vars still work without it
    pass


@dataclass(frozen=True)
class Config:
    price_list_api_endpoint: str = os.getenv(
        "PLAN_COSTS_PRICE_LIST_API_ENDPOINT",
        "http://localhost:4000/graphql",
    )


# single shared config instance
CONFIG = Config()
