from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from ..api_tokens import ApiTokenRow
from ..quota import TenantUsage


@dataclass(frozen=True)
class TenantSummary:
    id: UUID
    name: str
    slug: str
    role: str
    plan: str = "free"


@dataclass
class Tenant:
    id: UUID
    name: str
    slug: str
    plan: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    created_at: datetime


@dataclass
class MemberRow:
    user_id: UUID
    email: str | None
    role: str
    created_at: datetime


@dataclass
class InvitationRow:
    id: UUID
    tenant_id: UUID
    email: str
    role: str
    token: str
    invited_by: UUID
    expires_at: datetime
    accepted_at: datetime | None
    accepted_by: UUID | None
    created_at: datetime


@dataclass
class DocumentRow:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    status: str = "uploaded"
    error: str | None = None
    created_at: datetime | None = None


@dataclass
class SessionRow:
    id: UUID
    tenant_id: UUID
    user_id: UUID
    started_at: datetime
    ended_at: datetime | None
    language: str | None
    raw_words: list[dict]
    refined_turns: list[dict]
    meta: dict


class Database:
    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 10) -> None:
        self._dsn = dsn
        self._min = min_size
        self._max = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn, min_size=self._min, max_size=self._max)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _pool_required(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._pool

    # ----- membership --------------------------------------------------------

    async def is_member(self, user_id: str, tenant_id: UUID) -> bool:
        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM app.tenant_members WHERE user_id = $1 AND tenant_id = $2",
                UUID(user_id),
                tenant_id,
            )
            return row is not None

    async def list_user_tenants(self, user_id: str) -> list[TenantSummary]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.id, t.name, t.slug, t.plan, m.role::text AS role
                FROM app.tenants t
                JOIN app.tenant_members m ON m.tenant_id = t.id
                WHERE m.user_id = $1
                ORDER BY t.name
                """,
                UUID(user_id),
            )
            return [
                TenantSummary(
                    id=r["id"], name=r["name"], slug=r["slug"], role=r["role"], plan=r["plan"]
                )
                for r in rows
            ]

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, name, slug, plan, stripe_customer_id, stripe_subscription_id, created_at
                FROM app.tenants WHERE id = $1
                """,
                tenant_id,
            )
            if r is None:
                return None
            return Tenant(**dict(r))

    async def create_tenant_with_owner(
        self, name: str, slug: str, user_id: str
    ) -> TenantSummary:
        async with self._pool_required().acquire() as conn, conn.transaction():
            tenant = await conn.fetchrow(
                "INSERT INTO app.tenants (name, slug) VALUES ($1, $2) RETURNING id, name, slug, plan",
                name,
                slug,
            )
            await conn.execute(
                """
                INSERT INTO app.tenant_members (user_id, tenant_id, role)
                VALUES ($1, $2, 'owner')
                """,
                UUID(user_id),
                tenant["id"],
            )
            return TenantSummary(
                id=tenant["id"],
                name=tenant["name"],
                slug=tenant["slug"],
                role="owner",
                plan=tenant["plan"],
            )

    async def list_members(self, tenant_id: UUID) -> list[MemberRow]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.user_id, u.email, m.role::text AS role, m.created_at
                FROM app.tenant_members m
                LEFT JOIN auth.users u ON u.id = m.user_id
                WHERE m.tenant_id = $1
                ORDER BY m.created_at
                """,
                tenant_id,
            )
            return [MemberRow(**dict(r)) for r in rows]

    async def get_member_role(self, tenant_id: UUID, user_id: str) -> str | None:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchval(
                "SELECT role::text FROM app.tenant_members WHERE tenant_id = $1 AND user_id = $2",
                tenant_id,
                UUID(user_id),
            )
            return r

    async def remove_member(self, tenant_id: UUID, user_id: str) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                "DELETE FROM app.tenant_members WHERE tenant_id = $1 AND user_id = $2",
                tenant_id,
                UUID(user_id),
            )

    async def count_tenant_members(self, tenant_id: UUID) -> int:
        async with self._pool_required().acquire() as conn:
            return await conn.fetchval(
                "SELECT count(*) FROM app.tenant_members WHERE tenant_id = $1", tenant_id
            )

    # ----- invitations -------------------------------------------------------

    async def create_invitation(
        self,
        tenant_id: UUID,
        email: str,
        role: str,
        invited_by: UUID,
        token: str,
        expires_at: datetime,
    ) -> InvitationRow:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow(
                """
                INSERT INTO app.invitations
                    (tenant_id, email, role, invited_by, token, expires_at)
                VALUES ($1, $2, $3::app.member_role, $4, $5, $6)
                RETURNING *
                """,
                tenant_id,
                email.lower(),
                role,
                invited_by,
                token,
                expires_at,
            )
            return InvitationRow(**{k: r[k] for k in r.keys()})

    async def list_invitations(self, tenant_id: UUID) -> list[InvitationRow]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM app.invitations WHERE tenant_id = $1 AND accepted_at IS NULL ORDER BY created_at DESC",
                tenant_id,
            )
            return [InvitationRow(**{k: r[k] for k in r.keys()}) for r in rows]

    async def get_invitation_by_token(self, token: str) -> InvitationRow | None:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow("SELECT * FROM app.invitations WHERE token = $1", token)
            return InvitationRow(**{k: r[k] for k in r.keys()}) if r else None

    async def delete_invitation(self, invitation_id: UUID, tenant_id: UUID) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                "DELETE FROM app.invitations WHERE id = $1 AND tenant_id = $2",
                invitation_id,
                tenant_id,
            )

    async def accept_invitation(
        self, invitation: InvitationRow, user_id: str
    ) -> None:
        async with self._pool_required().acquire() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO app.tenant_members (user_id, tenant_id, role)
                VALUES ($1, $2, $3::app.member_role)
                ON CONFLICT (user_id, tenant_id) DO NOTHING
                """,
                UUID(user_id),
                invitation.tenant_id,
                invitation.role,
            )
            await conn.execute(
                """
                UPDATE app.invitations
                SET accepted_at = now(), accepted_by = $2
                WHERE id = $1
                """,
                invitation.id,
                UUID(user_id),
            )

    # ----- billing / plan ----------------------------------------------------

    async def set_tenant_plan(
        self,
        tenant_id: UUID,
        plan: str,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                UPDATE app.tenants
                SET plan = $2,
                    stripe_customer_id = COALESCE($3, stripe_customer_id),
                    stripe_subscription_id = COALESCE($4, stripe_subscription_id)
                WHERE id = $1
                """,
                tenant_id,
                plan,
                stripe_customer_id,
                stripe_subscription_id,
            )

    async def get_tenant_usage(self, tenant_id: UUID) -> TenantUsage:
        async with self._pool_required().acquire() as conn:
            plan = await conn.fetchval(
                "SELECT plan FROM app.tenants WHERE id = $1", tenant_id
            ) or "free"
            seconds = await conn.fetchval(
                """
                SELECT COALESCE(
                    SUM(EXTRACT(EPOCH FROM (COALESCE(ended_at, now()) - started_at))),
                    0
                )::int
                FROM app.sessions
                WHERE tenant_id = $1
                  AND started_at >= date_trunc('month', now())
                """,
                tenant_id,
            )
            docs = await conn.fetchval(
                """
                SELECT count(*)::int FROM app.documents
                WHERE tenant_id = $1 AND created_at >= date_trunc('month', now())
                """,
                tenant_id,
            )
            return TenantUsage(plan=plan, transcription_seconds=int(seconds or 0), documents=int(docs or 0))

    # ----- sessions (M4) -----------------------------------------------------

    async def insert_session(self, row: SessionRow) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO app.sessions
                    (id, tenant_id, user_id, started_at, ended_at, language,
                     raw_words, refined_turns, meta)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    raw_words = EXCLUDED.raw_words,
                    refined_turns = EXCLUDED.refined_turns,
                    meta = EXCLUDED.meta
                """,
                row.id, row.tenant_id, row.user_id, row.started_at, row.ended_at,
                row.language, json.dumps(row.raw_words), json.dumps(row.refined_turns),
                json.dumps(row.meta),
            )

    async def list_sessions(self, tenant_id: UUID, limit: int = 50) -> list[dict]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, started_at, ended_at, language,
                       jsonb_array_length(raw_words) AS raw_word_count,
                       jsonb_array_length(refined_turns) AS refined_turn_count
                FROM app.sessions
                WHERE tenant_id = $1
                ORDER BY started_at DESC
                LIMIT $2
                """,
                tenant_id, limit,
            )
            return [dict(r) for r in rows]

    async def get_session(self, session_id: UUID, tenant_id: UUID) -> dict | None:
        async with self._pool_required().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, user_id, started_at, ended_at, language,
                       raw_words, refined_turns, meta
                FROM app.sessions
                WHERE id = $1 AND tenant_id = $2
                """,
                session_id, tenant_id,
            )
            return dict(row) if row else None

    # ----- documents (M4) ----------------------------------------------------

    async def insert_document(self, row: DocumentRow) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO app.documents
                    (id, tenant_id, user_id, filename, content_type, size_bytes,
                     storage_path, status, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                row.id, row.tenant_id, row.user_id, row.filename, row.content_type,
                row.size_bytes, row.storage_path, row.status, row.error,
            )

    async def get_document(self, doc_id: UUID) -> DocumentRow | None:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, tenant_id, user_id, filename, content_type, size_bytes,
                       storage_path, status, error, created_at
                FROM app.documents WHERE id = $1
                """,
                doc_id,
            )
            return DocumentRow(**dict(r)) if r else None

    async def list_documents(self, tenant_id: UUID, limit: int = 50) -> list[DocumentRow]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, user_id, filename, content_type, size_bytes,
                       storage_path, status, error, created_at
                FROM app.documents
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tenant_id, limit,
            )
            return [DocumentRow(**dict(r)) for r in rows]

    async def set_document_status(
        self, doc_id: UUID, status: str, error: str | None = None
    ) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                "UPDATE app.documents SET status = $2, error = $3 WHERE id = $1",
                doc_id, status, error,
            )

    async def record_entity_source(
        self,
        tenant_id: UUID,
        entity_id: str,
        source_type: str,
        source_ref: UUID | None,
        needs_enrichment: bool = False,
    ) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO app.entity_sources
                    (tenant_id, entity_id, source_type, source_ref, needs_enrichment)
                VALUES ($1, $2, $3, $4, $5)
                """,
                tenant_id, entity_id, source_type, source_ref, needs_enrichment,
            )

    # ----- API tokens --------------------------------------------------------

    async def create_api_token(
        self,
        tenant_id: UUID,
        user_id: UUID,
        name: str,
        prefix: str,
        token_hash: str,
    ) -> ApiTokenRow:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow(
                """
                INSERT INTO app.api_tokens (tenant_id, user_id, name, prefix, token_hash)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, tenant_id, user_id, name, prefix, last_used_at, revoked_at, created_at
                """,
                tenant_id, user_id, name, prefix, token_hash,
            )
            return ApiTokenRow(**dict(r))

    async def list_api_tokens(self, tenant_id: UUID) -> list[ApiTokenRow]:
        async with self._pool_required().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, user_id, name, prefix, last_used_at, revoked_at, created_at
                FROM app.api_tokens
                WHERE tenant_id = $1 AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                tenant_id,
            )
            return [ApiTokenRow(**dict(r)) for r in rows]

    async def get_api_token_by_hash(self, token_hash: str) -> ApiTokenRow | None:
        async with self._pool_required().acquire() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, tenant_id, user_id, name, prefix, last_used_at, revoked_at, created_at
                FROM app.api_tokens
                WHERE token_hash = $1 AND revoked_at IS NULL
                """,
                token_hash,
            )
            return ApiTokenRow(**dict(r)) if r else None

    async def touch_api_token(self, token_id: UUID) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                "UPDATE app.api_tokens SET last_used_at = now() WHERE id = $1", token_id
            )

    async def revoke_api_token(self, token_id: UUID, tenant_id: UUID) -> None:
        async with self._pool_required().acquire() as conn:
            await conn.execute(
                """
                UPDATE app.api_tokens SET revoked_at = now()
                WHERE id = $1 AND tenant_id = $2 AND revoked_at IS NULL
                """,
                token_id, tenant_id,
            )
