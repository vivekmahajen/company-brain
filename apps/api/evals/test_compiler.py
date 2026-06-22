"""§9: handle-refund compiles with thresholds, bindings, guardrails, provenance."""
import os

from apps.api.config import get_settings
from apps.api.services.execution import get_skill


def test_skill_file_written(seeded):
    path = os.path.join(get_settings().skills_dir, "handle-refund.skill.md")
    assert os.path.exists(path)
    body = open(path).read()
    assert "slug: handle-refund" in body
    assert "approval_required_when:" in body


def test_skill_has_thresholds_and_bindings(seeded, db, org_id):
    skill = get_skill(db, "handle-refund", org_id)
    assert skill is not None
    body = skill["body_md"]
    # explicit decision thresholds, not prose
    assert "500" in body and "30 days" in body and "90 days" in body
    # tool bindings with approval gate on high-value refunds
    tools = {t["name"]: t for t in skill["tools"]}
    assert tools["stripe_refund"]["side_effecting"] is True
    assert tools["stripe_refund"]["approval_required"] is True
    assert "amount > 500" in (tools["stripe_refund"]["approval_expression"] or "")
    # provenance footnotes present
    assert len(skill["provenance"]) >= 2
    # side-effecting skill is gated for review, never auto-approved
    assert skill["status"] == "needs_review"


def test_guardrails_present(seeded, db, org_id):
    skill = get_skill(db, "handle-refund", org_id)
    guardrails = " ".join(skill["frontmatter"]["guardrails"]).lower()
    assert "90 days" in guardrails
    assert "exceed" in guardrails
