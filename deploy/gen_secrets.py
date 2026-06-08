"""
Generate Supabase self-hosted secrets for hugorm.

Emits env-file lines to stdout. Usage:
    uv run python deploy/gen_secrets.py > deploy/.env
"""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jwt  # noqa: E402


def main() -> None:
    jwt_secret = secrets.token_hex(32)
    pg_password = secrets.token_urlsafe(24)
    now = int(time.time())
    long_exp = now + 10 * 365 * 24 * 3600  # 10 years

    anon = jwt.encode(
        {"role": "anon", "iss": "supabase", "iat": now, "exp": long_exp},
        jwt_secret,
        algorithm="HS256",
    )
    service = jwt.encode(
        {"role": "service_role", "iss": "supabase", "iat": now, "exp": long_exp},
        jwt_secret,
        algorithm="HS256",
    )

    print(f"POSTGRES_PASSWORD={pg_password}")
    print(f"JWT_SECRET={jwt_secret}")
    print(f"ANON_KEY={anon}")
    print(f"SERVICE_ROLE_KEY={service}")
    print("JWT_EXPIRY=3600")
    print("SITE_URL=http://localhost:8002")
    print("API_EXTERNAL_URL=http://localhost:9999")
    print("ADDITIONAL_REDIRECT_URLS=http://localhost:8002/**")
    print("DISABLE_SIGNUP=false")


if __name__ == "__main__":
    main()
