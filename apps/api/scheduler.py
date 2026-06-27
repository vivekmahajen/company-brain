"""Background refresh — Phase 2 finisher.

Re-syncs every tenant's connected sources and, only when new artifacts actually
land, re-extracts → synthesizes → recompiles for that tenant. The cost guard
(extract only on new data) keeps a scheduled run cheap on a paid LLM.

Run it as a Railway cron command:

    python -m apps.api.scheduler

or trigger it over HTTP (admin-gated): POST /api/admin/refresh
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.skill_compiler import compile_skill
from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.extraction.extractor import extract_pending
from apps.api.graph.synthesis import synthesize
from apps.api.models.tables import Org
from apps.api.resolver.resolver import sync_resolver
from apps.api.services.ingest import sync_connected_sources


def _new_artifacts(synced: list[dict]) -> int:
    return sum(r.get("inserted", 0) for r in synced if isinstance(r, dict))


def refresh_tenant(db: Session, org_id: str, *, process: bool = True) -> dict:
    """Sync a tenant's connected sources; re-process only if new artifacts landed."""
    synced = sync_connected_sources(db, org_id)
    new = _new_artifacts(synced)
    out: dict = {"org_id": org_id, "synced": synced, "new_artifacts": new, "processed": False}
    if process and new > 0:
        out["extract"] = extract_pending(db, org_id)
        synthesize(db, org_id)
        for topic in SKILL_TEMPLATES:
            compile_skill(db, org_id, topic)
        sync_resolver(db, org_id)
        out["processed"] = True
    return out


def refresh_all_tenants(db: Session, *, process: bool = True) -> dict:
    """Refresh every active tenant. Cheap when nothing changed (sync only)."""
    from apps.api.services.orgs import ensure_default_org

    ensure_default_org(db)
    orgs = db.scalars(select(Org).where(Org.status == "active")).all()
    results = [refresh_tenant(db, o.id, process=process) for o in orgs]
    return {
        "tenants": len(orgs),
        "tenants_with_new_data": sum(1 for r in results if r["new_artifacts"] > 0),
        "results": results,
    }


def main() -> None:
    from apps.api.models.db import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        summary = refresh_all_tenants(db)
        print(f"refreshed {summary['tenants']} tenants · "
              f"{summary['tenants_with_new_data']} had new data")
        for r in summary["results"]:
            if r["new_artifacts"]:
                print(f"  {r['org_id'][:8]}: +{r['new_artifacts']} artifacts, processed={r['processed']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
