from __future__ import annotations

import time

import jwt as pyjwt
import pytest

from hugorm.auth.jwt import InvalidTokenError, JWTVerifier


SECRET = "test-secret-that-is-plenty-long"


def _mint(claims: dict, secret: str = SECRET) -> str:
    return pyjwt.encode(claims, secret, algorithm="HS256")


def _valid_claims(**overrides) -> dict:
    now = int(time.time())
    base = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "email": "a@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    base.update(overrides)
    return base


def test_verifies_valid_token_and_extracts_user() -> None:
    v = JWTVerifier(SECRET)
    user = v.verify(_mint(_valid_claims()))
    assert user.id == "11111111-1111-1111-1111-111111111111"
    assert user.email == "a@example.com"
    assert user.role == "authenticated"


def test_rejects_bad_signature() -> None:
    v = JWTVerifier(SECRET)
    token = _mint(_valid_claims(), secret="wrong-secret")
    with pytest.raises(InvalidTokenError):
        v.verify(token)


def test_rejects_expired_token() -> None:
    v = JWTVerifier(SECRET)
    token = _mint(_valid_claims(exp=int(time.time()) - 10))
    with pytest.raises(InvalidTokenError):
        v.verify(token)


def test_rejects_wrong_audience() -> None:
    v = JWTVerifier(SECRET, audience="authenticated")
    token = _mint(_valid_claims(aud="anon"))
    with pytest.raises(InvalidTokenError):
        v.verify(token)


def test_rejects_missing_subject() -> None:
    v = JWTVerifier(SECRET)
    claims = _valid_claims()
    del claims["sub"]
    token = _mint(claims)
    with pytest.raises(InvalidTokenError):
        v.verify(token)


def test_empty_secret_rejected_at_init() -> None:
    with pytest.raises(ValueError):
        JWTVerifier("")
