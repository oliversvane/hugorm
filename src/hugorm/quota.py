from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanLimits:
    plan: str
    transcription_seconds_per_month: int
    documents_per_month: int
    workspaces_per_user: int


FREE = PlanLimits(
    plan="free",
    transcription_seconds_per_month=60 * 60,  # 60 minutes
    documents_per_month=10,
    workspaces_per_user=1,
)

PRO = PlanLimits(
    plan="pro",
    transcription_seconds_per_month=100 * 60 * 60,  # 100 hours
    documents_per_month=100,
    workspaces_per_user=10,
)

LIMITS = {"free": FREE, "pro": PRO}


def get_limits(plan: str) -> PlanLimits:
    return LIMITS.get(plan, FREE)


@dataclass
class TenantUsage:
    plan: str
    transcription_seconds: int
    documents: int

    def to_dict(self) -> dict:
        limits = get_limits(self.plan)
        return {
            "plan": self.plan,
            "transcription": {
                "used_seconds": self.transcription_seconds,
                "limit_seconds": limits.transcription_seconds_per_month,
            },
            "documents": {
                "used": self.documents,
                "limit": limits.documents_per_month,
            },
        }
