"""Plan quota enforcement (Phase 6).

A single choke point the action endpoints call before allowing a billable action:
connecting a source, authoring a capability, or spending on extraction. Returns
(ok, reason) — over-quota reasons surface as 402 Payment Required with an upgrade hint.
Enterprise / unlimited plans always pass.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.billing.metering import connected_source_count, get_plan, period_extraction_usd
from apps.api.billing.plans import plan_limits
from apps.api.models.tables import SkillTemplate


def check_quota(db: Session, org_id: str, resource: str) -> tuple[bool, str | None]:
    limits = plan_limits(get_plan(db, org_id))

    if resource == "source":
        cap = limits["max_sources"]
        if cap is not None and connected_source_count(db, org_id) >= cap:
            return False, f"plan limit reached: {cap} sources. Upgrade to connect more."

    elif resource == "capability":
        cap = limits["max_custom_capabilities"]
        if cap is not None:
            used = db.scalar(select(func.count(SkillTemplate.id)).where(
                SkillTemplate.org_id == org_id)) or 0
            if used >= cap:
                return False, f"plan limit reached: {cap} custom capabilities. Upgrade to add more."

    elif resource == "extraction":
        cap = limits["monthly_extraction_usd"]
        if cap is not None and period_extraction_usd(db, org_id) >= cap:
            return False, f"monthly extraction budget reached (${cap}). Upgrade to keep ingesting."

    return True, None
