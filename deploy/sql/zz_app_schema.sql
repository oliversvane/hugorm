-- hugorm application schema. Applied by supabase/postgres container init
-- on first boot only. For subsequent migrations, apply manually via psql.

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON t.typnamespace = n.oid
        WHERE t.typname = 'member_role' AND n.nspname = 'app'
    ) THEN
        CREATE TYPE app.member_role AS ENUM ('owner', 'admin', 'member');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS app.tenant_members (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    role app.member_role NOT NULL DEFAULT 'member',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_members_tenant ON app.tenant_members(tenant_id);

-- M4: transcript persistence. One row per completed session with raw words
-- and refined turns as JSONB blobs. Normalize later if query patterns demand it.
CREATE TABLE IF NOT EXISTS app.sessions (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    language TEXT,
    raw_words JSONB NOT NULL DEFAULT '[]'::jsonb,
    refined_turns JSONB NOT NULL DEFAULT '[]'::jsonb,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant_started ON app.sessions (tenant_id, started_at DESC);

-- M4: document ingestion. Binary lives in Supabase Storage; this tracks
-- metadata + processing status.
CREATE TABLE IF NOT EXISTS app.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_tenant_created ON app.documents (tenant_id, created_at DESC);

-- M4: entity provenance. Entities live in the tenant's Kuzu graph; this
-- log records each place the entity was mentioned (multiple rows per entity).
CREATE TABLE IF NOT EXISTS app.entity_sources (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('document', 'transcript', 'manual')),
    source_ref UUID,
    needs_enrichment BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_sources_tenant_entity ON app.entity_sources (tenant_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_sources_source_ref ON app.entity_sources (source_ref);
