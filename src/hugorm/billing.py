from __future__ import annotations

import logging
from dataclasses import dataclass

import stripe

from .config import Settings

logger = logging.getLogger(__name__)


class BillingDisabled(RuntimeError):
    pass


@dataclass
class CheckoutResult:
    tenant_id: str
    customer_id: str | None
    subscription_id: str | None


def _configure(settings: Settings) -> None:
    if not settings.stripe_secret_key:
        raise BillingDisabled("Stripe not configured")
    stripe.api_key = settings.stripe_secret_key


def create_checkout_url(
    settings: Settings, tenant_id: str, customer_email: str | None
) -> str:
    _configure(settings)
    if not settings.stripe_price_id:
        raise BillingDisabled("HUGORM_STRIPE_PRICE_ID not configured")
    kwargs: dict = {
        "mode": "subscription",
        "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
        "success_url": (
            f"{settings.frontend_url}/settings?upgraded=1&session_id={{CHECKOUT_SESSION_ID}}"
        ),
        "cancel_url": f"{settings.frontend_url}/settings",
        "metadata": {"tenant_id": tenant_id},
    }
    if customer_email:
        kwargs["customer_email"] = customer_email
    session = stripe.checkout.Session.create(**kwargs)
    return session.url


def verify_checkout(settings: Settings, session_id: str) -> CheckoutResult:
    _configure(settings)
    session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    if session.payment_status != "paid":
        raise BillingDisabled(f"checkout session not paid (status={session.payment_status})")
    sub = session.subscription
    sub_id = sub.id if sub and not isinstance(sub, str) else (sub if isinstance(sub, str) else None)
    return CheckoutResult(
        tenant_id=session.metadata.get("tenant_id", ""),
        customer_id=session.customer if isinstance(session.customer, str) else (session.customer.id if session.customer else None),
        subscription_id=sub_id,
    )
