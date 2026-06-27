"""Phase-2 background refresh: re-sync connected sources across tenants, and
re-process only when new artifacts land (cost guard). Offline (fixture-backed)."""
from __future__ import annotations

from apps.api.scheduler import refresh_all_tenants, refresh_tenant
from apps.api.services.connections import connect_source
from apps.api.services.orgs import create_org


def test_refresh_processes_only_when_new_artifacts_land(seeded, db):
    org = create_org(db, name="RefreshCo")["id"]
    connect_source(db, org, kind="slack", name="rc workspace",
                   config={"fixture_path": "fixtures/slack/support.json", "acl_groups": ["support-team"]})

    # first refresh: the connected source has new artifacts → processed
    r1 = refresh_tenant(db, org)
    assert r1["new_artifacts"] >= 1 and r1["processed"] is True

    # second refresh: nothing new (idempotent sync) → NOT processed (no extraction spend)
    r2 = refresh_tenant(db, org)
    assert r2["new_artifacts"] == 0 and r2["processed"] is False


def test_refresh_all_tenants_covers_active_orgs(seeded, db):
    a = create_org(db, name="A-co")["id"]
    b = create_org(db, name="B-co")["id"]
    connect_source(db, a, kind="slack", name="a ws",
                   config={"fixture_path": "fixtures/slack/support.json"})
    summary = refresh_all_tenants(db, process=False)  # sync-only
    org_ids = {r["org_id"] for r in summary["results"]}
    assert a in org_ids and b in org_ids
    assert summary["tenants"] >= 2
