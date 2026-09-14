"""Small production-safe API guard used before full tenant authentication."""
from __future__ import annotations

import os
import secrets


def configured_token() -> str | None:
    value = os.getenv("BANBOOS2_API_TOKEN", "").strip()
    return value or None


def is_production() -> bool:
    return os.getenv("BANBOOS2_ENV", "development").lower() in {"prod", "production"}


def token_matches(candidate: str | None) -> bool:
    token = configured_token()
    return bool(token and candidate and secrets.compare_digest(candidate, token))
