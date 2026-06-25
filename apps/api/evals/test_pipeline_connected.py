"""pipeline/run must sync tenant-connected sources, not just the bundled fixtures
(Phase 2). Uses a fixture-backed connected source so no network is needed."""
from __future__ import annotations

from sqlalchemy import select

from apps.api.models.tables import Artifact
from apps.api.services.connections import connect_source
from apps.api.services.orgs import create_org
from apps.api.services.pipeline import run_full_pipeline


def test_pipeline_run_syncs_connected_sources(seeded, db):
    org = create_org(db, name="PipeCo")["id"]  # provisions fixtures (connected source not yet present)

    # connect a NON-default source (distinct name so it isn't treated as a fixture)
    view = connect_source(db, org, kind="slack", name="my custom workspace",
                          config={"fixture_path": "fixtures/slack/support.json", "acl_groups": ["support-team"]})

    report = run_full_pipeline(db, org)

    # it shows up in the ingest results...
    assert "my custom workspace" in [r.get("source") for r in report["ingest"]]
    # ...and its artifacts actually landed under this org
    landed = db.scalar(select(Artifact.id).where(
        Artifact.org_id == org, Artifact.source_id == view["id"]).limit(1))
    assert landed is not None


def test_pipeline_run_isolates_a_failing_connected_source(seeded, db):
    """A connected source that errors on sync must not break the whole pipeline."""
    org = create_org(db, name="FlakyCo")["id"]
    # 'mode: live' with no credentials → the connector raises at sync time
    bad = connect_source(db, org, kind="github", name="broken (live)",
                         config={"mode": "live"})
    report = run_full_pipeline(db, org)
    # the run still completes and reports the per-source error
    errored = [r for r in report["ingest"] if r.get("source") == "broken (live)"]
    assert errored and "error" in errored[0]
    assert report["skills"]  # the rest of the pipeline still produced skills
