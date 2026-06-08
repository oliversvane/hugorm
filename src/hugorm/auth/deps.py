from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Request, status

from ..api_tokens import hash_token, looks_like_api_token
from .jwt import InvalidTokenError, JWTVerifier


@dataclass
class AuthContext:
    user_id: str
    email: str | None
    role: str
    source: Literal["jwt", "api_token"]
    tenant_id: UUID | None = None
    api_token_id: UUID | None = None


async def auth_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthContext:
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing Authorization header")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "expected 'Bearer <token>'")
    token = parts[1].strip()

    if looks_like_api_token(token):
        db = getattr(request.app.state, "db", None)
        if db is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not configured")
        row = await db.get_api_token_by_hash(hash_token(token))
        if row is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked API token")
        await db.touch_api_token(row.id)
        return AuthContext(
            user_id=str(row.user_id),
            email=None,
            role="authenticated",
            source="api_token",
            tenant_id=row.tenant_id,
            api_token_id=row.id,
        )

    verifier: JWTVerifier | None = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth not configured")
    try:
        user = verifier.verify(token)
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    return AuthContext(
        user_id=user.id,
        email=user.email,
        role=user.role,
        source="jwt",
    )


async def current_user(ctx: AuthContext = Depends(auth_context)) -> AuthContext:
    return ctx


async def active_tenant(
    request: Request,
    ctx: AuthContext = Depends(auth_context),
    tenant: str | None = Query(default=None),
) -> tuple[AuthContext, UUID]:
    if ctx.tenant_id is not None:
        return ctx, ctx.tenant_id
    if tenant is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant query parameter required")
    try:
        tid = UUID(tenant)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tenant must be a UUID") from e
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database not configured")
    if not await db.is_member(ctx.user_id, tid):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this tenant")
    return ctx, tid


async def require_role(
    auth: tuple[AuthContext, UUID],
    request: Request,
    roles: set[str],
) -> tuple[AuthContext, UUID]:
    ctx, tenant_id = auth
    db = request.app.state.db
    role = await db.get_member_role(tenant_id, ctx.user_id)
    if role is None or role not in roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"requires one of roles: {sorted(roles)}"
        )
    return ctx, tenant_id
