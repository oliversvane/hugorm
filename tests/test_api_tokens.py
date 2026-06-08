from __future__ import annotations

from hugorm.api_tokens import generate, hash_token, looks_like_api_token


def test_generate_returns_matching_hash() -> None:
    token, prefix, digest = generate()
    assert token.startswith("hgrm_")
    assert len(prefix) == 8
    assert hash_token(token) == digest


def test_generate_is_unique() -> None:
    t1, _, _ = generate()
    t2, _, _ = generate()
    assert t1 != t2


def test_looks_like_api_token() -> None:
    assert looks_like_api_token("hgrm_abc")
    assert not looks_like_api_token("eyJ...")
    assert not looks_like_api_token("")
