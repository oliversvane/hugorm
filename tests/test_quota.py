from __future__ import annotations

from hugorm.quota import FREE, PRO, TenantUsage, get_limits


def test_free_and_pro_have_distinct_limits() -> None:
    assert FREE.plan == "free"
    assert PRO.plan == "pro"
    assert PRO.transcription_seconds_per_month > FREE.transcription_seconds_per_month
    assert PRO.documents_per_month > FREE.documents_per_month


def test_get_limits_falls_back_to_free() -> None:
    assert get_limits("free") is FREE
    assert get_limits("pro") is PRO
    assert get_limits("enterprise") is FREE


def test_tenant_usage_serialises_with_limits() -> None:
    u = TenantUsage(plan="free", transcription_seconds=600, documents=2)
    d = u.to_dict()
    assert d["plan"] == "free"
    assert d["transcription"]["limit_seconds"] == FREE.transcription_seconds_per_month
    assert d["documents"]["limit"] == FREE.documents_per_month
