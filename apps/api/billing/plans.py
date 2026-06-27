"""Plan tiers (Phase 6). Limits gate sources, custom capabilities, and monthly
extraction spend. `None` = unlimited. Prices are display-only here; real charging
goes through the Stripe seam (later slice)."""
from __future__ import annotations

PLANS: dict[str, dict] = {
    "free": {
        "label": "Free",
        "price_usd_month": 0,
        "max_sources": 2,
        "max_custom_capabilities": 1,
        "monthly_extraction_usd": 1.0,
    },
    "team": {
        "label": "Team",
        "price_usd_month": 99,
        "max_sources": 10,
        "max_custom_capabilities": 10,
        "monthly_extraction_usd": 50.0,
    },
    "business": {
        "label": "Business",
        "price_usd_month": 499,
        "max_sources": 50,
        "max_custom_capabilities": 100,
        "monthly_extraction_usd": 500.0,
    },
    "enterprise": {
        "label": "Enterprise",
        "price_usd_month": None,  # custom
        "max_sources": None,
        "max_custom_capabilities": None,
        "monthly_extraction_usd": None,
    },
}

DEFAULT_PLAN = "free"


def plan_limits(plan: str) -> dict:
    return PLANS.get(plan, PLANS[DEFAULT_PLAN])


def is_valid_plan(plan: str) -> bool:
    return plan in PLANS
