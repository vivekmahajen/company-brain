"""Usage metering + plan lookup (Phase 6).

Records metered events (real model spend per tenant) and aggregates them per billing
period. The extraction cost is the one that actually moves money, so it's the headline
meter. Plan is read from the Subscription table (default: free)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.billing.plans import DEFAULT_PLAN, plan_limits
from apps.api.models.tables import Subscription, UsageEvent


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# --- plan / subscription --------------------------------------------------
def get_plan(db: Session, org_id: str) -> str:
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org_id))
    return sub.plan if sub else DEFAULT_PLAN


def set_plan(db: Session, org_id: str, plan: str) -> dict:
    from apps.api.billing.plans import is_valid_plan

    if not is_valid_plan(plan):
        return {"error": f"unknown plan '{plan}'"}
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org_id))
    if sub:
        sub.plan = plan
        sub.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Subscription(org_id=org_id, plan=plan))
    from apps.api.audit.log import record_audit

    record_audit(db, org_id, "billing.plan_change", actor="api", meta={"plan": plan})
    db.commit()
    return {"org_id": org_id, "plan": plan}


# --- metering -------------------------------------------------------------
def record_usage(db: Session, org_id: str, kind: str, *, cost_usd: float = 0.0, quantity: float = 1.0) -> None:
    """Append a usage event. Cheap; called from the hot path (extraction)."""
    if cost_usd <= 0 and quantity <= 0:
        return
    db.add(UsageEvent(org_id=org_id, kind=kind, quantity=quantity, cost_usd=cost_usd,
                      period=current_period()))
    db.flush()


def period_extraction_usd(db: Session, org_id: str, period: str | None = None) -> float:
    period = period or current_period()
    total = db.scalar(select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
        UsageEvent.org_id == org_id, UsageEvent.kind == "extraction", UsageEvent.period == period))
    return round(float(total or 0.0), 6)


def connected_source_count(db: Session, org_id: str) -> int:
    """Tenant-connected sources only — the bundled demo fixtures don't count toward
    a plan limit (a real tenant doesn't get the demo seed in production)."""
    from apps.api.models.tables import Source
    from apps.api.services.ingest import _default_keys

    defaults = _default_keys()
    rows = db.scalars(select(Source).where(Source.org_id == org_id)).all()
    return sum(1 for s in rows if (s.kind, s.name) not in defaults)


def usage_summary(db: Session, org_id: str) -> dict:
    from apps.api.models.tables import SkillTemplate

    plan = get_plan(db, org_id)
    limits = plan_limits(plan)
    sources = connected_source_count(db, org_id)
    custom_caps = db.scalar(select(func.count(SkillTemplate.id)).where(
        SkillTemplate.org_id == org_id)) or 0
    spend = period_extraction_usd(db, org_id)

    def remaining(used, cap):
        return None if cap is None else max(0, cap - used)

    return {
        "org_id": org_id,
        "plan": plan,
        "period": current_period(),
        "limits": limits,
        "usage": {
            "sources": int(sources),
            "custom_capabilities": int(custom_caps),
            "extraction_usd": spend,
        },
        "remaining": {
            "sources": remaining(int(sources), limits["max_sources"]),
            "custom_capabilities": remaining(int(custom_caps), limits["max_custom_capabilities"]),
            "extraction_usd": (None if limits["monthly_extraction_usd"] is None
                               else round(max(0.0, limits["monthly_extraction_usd"] - spend), 4)),
        },
    }
