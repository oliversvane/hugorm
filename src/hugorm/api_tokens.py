from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ApiTokenRow:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    name: str
    prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


def generate() -> tuple[str, str, str]:
    """Return (plaintext_token, display_prefix, sha256_hex)."""
    raw = secrets.token_hex(32)
    token = f"hgrm_{raw}"
    prefix = raw[:8]
    digest = hashlib.sha256(token.encode()).hexdigest()
    return token, prefix, digest


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_api_token(token: str) -> bool:
    return token.startswith("hgrm_")
