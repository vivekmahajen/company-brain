"""Permissions acceptance (§12). Worked example + PER=100% + leak detection.

The harness must turn red if visibility is widened — otherwise PER is theater.
"""
import pytest

from apps.api.evals.runners import permission
from apps.api.evals.runners.harness import _eval_token, setup_brain
from apps.api.evals.scoring import single_run_metrics
from apps.api.mcp.brain import MCPBrain
from apps.api.models.db import SessionLocal, init_db


@pytest.fixture(scope="module")
def eval_brain():
    init_db()
    db = SessionLocal()
    try:
        setup_brain(db)
    finally:
        db.close()


def _surfaces(token, slug):
    b = MCPBrain(_eval_token(token), transport="test")
    listed = {s["slug"] for s in b.call_tool("list_skills", {}).get("skills", [])}
    tools = {t["name"] for t in b.list_tools()}
    get_err = "error" in b.call_tool("get_skill", {"slug": slug})
    return slug in listed, any(n.startswith(f"{slug}__") for n in tools), not get_err


def test_worked_example_support_sees_refund(eval_brain):
    in_list, has_tool, can_get = _surfaces("agent-support-token", "handle-refund")
    assert in_list and has_tool and can_get


def test_worked_example_sales_cannot_see_refund(eval_brain):
    # Absent from list + tools + get (aggregation + existence leak prevented).
    in_list, has_tool, can_get = _surfaces("agent-sales-token", "handle-refund")
    assert not in_list and not has_tool and not can_get


def test_sales_sees_public_skills(eval_brain):
    in_list, _, can_get = _surfaces("agent-sales-token", "respond-to-incident")
    assert in_list and can_get


def test_per_is_100(eval_brain):
    db = SessionLocal()
    try:
        m = single_run_metrics(permission.run(db, split=None))
        assert m["PER"] == 1.0
    finally:
        db.close()


def test_harness_detects_a_permission_leak(eval_brain, monkeypatch):
    """Widen access (every source readable) → PER must drop below 100%."""
    db = SessionLocal()
    try:
        import apps.api.access.visibility as vis

        monkeypatch.setattr(vis, "can_access_source", lambda *a, **k: True)
        m = single_run_metrics(permission.run(db, split=None))
        assert m["PER"] < 1.0, "harness failed to detect a widened-visibility leak"
    finally:
        db.close()
