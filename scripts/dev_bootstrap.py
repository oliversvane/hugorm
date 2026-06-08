"""
Bootstrap a dev tenant + user + JWT for M3 testing without going through the
GoTrue signup flow.

Requires Postgres to be running (see deploy/docker-compose.yml).
Usage:
    uv run python scripts/dev_bootstrap.py --tenant-slug demo
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import asyncpg  # noqa: E402
import jwt  # noqa: E402

from hugorm.config import Settings  # noqa: E402


async def _run(args: argparse.Namespace) -> None:
    settings = Settings()
    dsn = args.database_url or settings.database_url
    secret = args.jwt_secret or settings.supabase_jwt_secret
    if not dsn:
        raise SystemExit("HUGORM_DATABASE_URL or --database-url required")
    if not secret:
        raise SystemExit("HUGORM_SUPABASE_JWT_SECRET or --jwt-secret required")

    user_id = uuid.uuid4()
    conn = await asyncpg.connect(dsn)
    try:
        tenant_row = await conn.fetchrow(
            """
            INSERT INTO app.tenants (name, slug)
            VALUES ($1, $2)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            args.tenant_name,
            args.tenant_slug,
        )
        tenant_id = tenant_row["id"]

        # Dev-only shortcut: insert a row directly into auth.users so the
        # foreign-key on tenant_members resolves. In prod, GoTrue creates this.
        await conn.execute(
            """
            INSERT INTO auth.users
                (id, aud, role, email, instance_id, email_confirmed_at)
            VALUES
                ($1, 'authenticated', 'authenticated', $2,
                 '00000000-0000-0000-0000-000000000000'::uuid, now())
            ON CONFLICT (id) DO NOTHING
            """,
            user_id,
            args.email,
        )
        await conn.execute(
            """
            INSERT INTO app.tenant_members (user_id, tenant_id, role)
            VALUES ($1, $2, 'owner')
            ON CONFLICT (user_id, tenant_id) DO UPDATE SET role = EXCLUDED.role
            """,
            user_id,
            tenant_id,
        )
    finally:
        await conn.close()

    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "email": args.email,
        "role": "authenticated",
        "aud": "authenticated",
        "iss": "supabase",
        "iat": now,
        "exp": now + args.exp_seconds,
    }
    token = jwt.encode(claims, secret, algorithm="HS256")

    print(f"tenant_id={tenant_id}")
    print(f"user_id={user_id}")
    print(f"token={token}")
    print()
    print("Next:")
    print(f"  uv run python scripts/seed_graph.py --tenant {tenant_id}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-name", default="Demo")
    ap.add_argument("--tenant-slug", default="demo")
    ap.add_argument("--email", default="dev@example.com")
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--jwt-secret", default=None)
    ap.add_argument("--exp-seconds", type=int, default=30 * 24 * 3600)
    args = ap.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
