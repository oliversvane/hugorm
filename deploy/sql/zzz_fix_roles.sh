#!/bin/sh
# Ran after migrate.sh. The supabase/postgres image creates several roles
# (supabase_auth_admin, authenticator, storage_admin) without setting their
# passwords — only supabase_admin gets its password aligned with
# $POSTGRES_PASSWORD. GoTrue then fails to connect. This script closes the
# gap for the roles hugorm actually uses.
set -eu

psql -v ON_ERROR_STOP=1 -U postgres -d postgres <<SQL
ALTER ROLE supabase_auth_admin WITH LOGIN PASSWORD '$POSTGRES_PASSWORD';
ALTER ROLE authenticator WITH LOGIN PASSWORD '$POSTGRES_PASSWORD';
ALTER ROLE supabase_storage_admin WITH LOGIN PASSWORD '$POSTGRES_PASSWORD';
SQL
