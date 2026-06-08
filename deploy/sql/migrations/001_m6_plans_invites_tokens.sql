-- M6 migration: tenant plans, invitations, API tokens.
-- Apply to a running DB with:
--   docker exec -i hugorm-postgres psql -U postgres -d postgres < deploy/sql/migrations/001_m6_plans_invites_tokens.sql

ALTER TABLE app.tenants
    ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro')),
    ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

CREATE TABLE IF NOT EXISTS app.invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role app.member_role NOT NULL DEFAULT 'member',
    token TEXT NOT NULL UNIQUE,
    invited_by UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    accepted_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invitations_tenant ON app.invitations (tenant_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON app.invitations (lower(email)) WHERE accepted_at IS NULL;

CREATE TABLE IF NOT EXISTS app.api_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES app.tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_tenant ON app.api_tokens (tenant_id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_hash_active ON app.api_tokens (token_hash) WHERE revoked_at IS NULL;
