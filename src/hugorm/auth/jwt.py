from __future__ import annotations

from dataclasses import dataclass

import jwt


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None
    role: str


class JWTVerifier:
    """
    Verifies Supabase-issued JWTs with the shared HS256 secret. Matches the
    signing scheme GoTrue uses by default.

    Dev tokens minted by scripts/dev_bootstrap.py are also HS256-signed with the
    same secret and verify through here.
    """

    def __init__(self, secret: str, audience: str = "authenticated") -> None:
        if not secret:
            raise ValueError("JWT secret is empty")
        self._secret = secret
        self._audience = audience

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as e:
            raise InvalidTokenError(str(e)) from e

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
            raise InvalidTokenError("token missing subject")
        return AuthenticatedUser(
            id=sub,
            email=payload.get("email"),
            role=payload.get("role", "authenticated"),
        )
