"""
Configuration and Environment Management.

Manages API credentials, endpoints, and headers in accordance with
security best practices and provider fair-access policies.
Never hardcodes secrets.
"""

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Optional[Path] = None) -> None:
    """Loads key-value pairs from a local .env file into os.environ if not already set."""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent / ".env"
    
    if not env_path.exists():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("\"'").strip()
            if key and key not in os.environ:
                os.environ[key] = val


# Automatically attempt to load local .env on import
load_env_file()


def get_sec_user_agent() -> str:
    """Returns the configured SEC EDGAR User-Agent header string."""
    return os.environ.get(
        "SEC_USER_AGENT",
        "FinancialIntelligenceResearchProject/1.0 (academic_research@university.edu)"
    )


def get_tiingo_api_key() -> Optional[str]:
    """Returns the Tiingo API token if configured in the environment."""
    return os.environ.get("TIINGO_API_KEY") or os.environ.get("TIINGO_TOKEN")


def get_finnhub_api_key() -> Optional[str]:
    """Returns the Finnhub API token if configured in the environment."""
    return os.environ.get("FINNHUB_API_KEY") or os.environ.get("FINNHUB_TOKEN")
