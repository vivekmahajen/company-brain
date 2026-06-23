"""E8 — Permission Enforcement Rate (PER). Deterministic sibling to GAR.

Drives the REAL MCPBrain serve path + VisibilityFilter against a golden access
matrix and an adversarial leak set (aggregation / existence / default-deny /
revocation / provenance). Any leak fails. PER = correct decisions / total.
"""
from __future__ import annotations

import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.access.visibility import VisibilityFilter
from apps.api.evals.runners.harness import EVAL_ORG, _eval_token, principal as eval_principal
from apps.api.mcp.brain import MCPBrain
from apps.api.models.access import Membership, SourceACL
from apps.api.models.tables import Skill

_GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "golden", "permission.json")


def _load() -> dict:
    with open(_GOLDEN, encoding="utf-8") as f:
        return json.load(f)


def _surfaces(token: str, slug: str) -> dict:
    """What the principal sees across every read surface."""
    brain = MCPBrain(_eval_token(token), transport="eval")
    listed = {s["slug"] for s in brain.call_tool("list_skills", {}).get("skills", [])}
    tools = {t["name"] for t in brain.list_tools()}
    has_wrapper = any(n.startswith(f"{slug}__") for n in tools)
    get_err = "error" in brain.call_tool("get_skill", {"slug": slug})
    return {"in_list": slug in listed, "has_wrapper": has_wrapper, "get_hidden": get_err}


def _matrix_case(case: dict) -> tuple[bool, dict]:
    s = _surfaces(case["token"], case["slug"])
    if case["expected"] == "visible":
        ok = s["in_list"] and s["has_wrapper"] and not s["get_hidden"]
    else:  # hidden everywhere (VIS-3/VIS-5)
        ok = (not s["in_list"]) and (not s["has_wrapper"]) and s["get_hidden"]
    return ok, {"expected": case["expected"], **s}


def _adversarial_case(db: Session, case: dict) -> tuple[bool, dict]:
    chk = case["check"]
    if chk == "aggregation_leak":
        s = _surfaces(case["token"], case["slug"])
        return (not s["in_list"] and not s["has_wrapper"] and s["get_hidden"]), s

    if chk == "existence_leak":
        brain = MCPBrain(_eval_token(case["token"]), transport="eval")
        hidden = brain.call_tool("get_skill", {"slug": case["slug"]})
        nonexistent = brain.call_tool("get_skill", {"slug": "no-such-skill-xyz"})
        return hidden == nonexistent, {"hidden": hidden, "nonexistent": nonexistent}

    if chk == "default_deny":
        # A principal with NO group memberships must see nothing.
        from apps.api.auth.principals import hash_token
        from apps.api.models.serving import Principal

        p = Principal(org_id=EVAL_ORG, kind="agent", display_name="no-groups",
                      scopes_jsonb=["invoke:*"], token_hash=hash_token("eval-nogroups"))
        db.add(p)
        db.commit()
        vf = VisibilityFilter(db, p)
        skills = db.scalars(select(Skill).where(Skill.org_id == EVAL_ORG, Skill.status == "approved")).all()
        visible = vf.filter_skills(skills)
        return len(visible) == 0, {"visible_count": len(visible)}

    if chk == "revocation":
        token, slug = case["token"], case["slug"]
        before = _surfaces(token, slug)["get_hidden"]  # False (visible)
        # Revoke support-team membership.
        p = eval_principal(db, token)
        from apps.api.models.access import Group

        support = db.scalar(select(Group).where(Group.org_id == EVAL_ORG, Group.name == "support-team"))
        mem = db.scalar(select(Membership).where(
            Membership.org_id == EVAL_ORG, Membership.principal_id == p.id, Membership.group_id == support.id))
        db.delete(mem)
        db.commit()
        after = _surfaces(token, slug)["get_hidden"]  # True (hidden) — no recompile
        # restore
        db.add(Membership(org_id=EVAL_ORG, principal_id=p.id, group_id=support.id, source_of_truth="mirror"))
        db.commit()
        return (before is False and after is True), {"before_hidden": before, "after_hidden": after}

    if chk == "provenance_redaction":
        # Defense-in-depth (VIS-6): deny one source for the principal, assert its
        # span is redacted from provenance even though they otherwise could see it.
        token, slug = case["token"], case["slug"]
        p = eval_principal(db, token)
        skill = db.scalars(select(Skill).where(
            Skill.org_id == EVAL_ORG, Skill.slug == slug).order_by(Skill.version.desc())).first()
        from apps.api.access.propagation import skill_sources
        from apps.api.models.tables import Source

        slack_src = next((sid for sid in skill_sources(db, skill)
                          if (db.get(Source, sid) or Source()).kind == "slack"), None)
        full = VisibilityFilter(db, p).filter_provenance(skill)
        deny = SourceACL(org_id=EVAL_ORG, source_id=slack_src, subject_id=p.id,
                         subject_kind="principal", access="deny", origin="brain")
        db.add(deny)
        db.commit()
        redacted = VisibilityFilter(db, p).filter_provenance(skill)
        db.delete(deny)
        db.commit()
        had_slack = any("slack" in e["source"] for e in full)
        no_slack = not any("slack" in e["source"] for e in redacted)
        return (had_slack and no_slack and len(redacted) < len(full)), {
            "full": len(full), "redacted": len(redacted)}

    return False, {"detail": f"unknown check {chk}"}


def run(db: Session, split: str | None = "test") -> list[dict]:
    data = _load()
    results = []
    for case in data["matrix"]:
        if split and case["split"] != split:
            continue
        try:
            ok, detail = _matrix_case(case)
        except Exception as e:  # noqa: BLE001 - fail closed
            ok, detail = False, {"error": f"{type(e).__name__}: {e}"}
        results.append({"stage": "permission", "case_id": case["id"], "tier": case["tier"],
                        "split": case["split"], "passed": ok, "judge_used": False,
                        "error": detail.get("error"), "detail": detail})
    for case in data["adversarial"]:
        if split and case["split"] != split:
            continue
        try:
            ok, detail = _adversarial_case(db, case)
        except Exception as e:  # noqa: BLE001 - fail closed
            ok, detail = False, {"error": f"{type(e).__name__}: {e}"}
        results.append({"stage": "permission", "case_id": case["id"], "tier": case["tier"],
                        "split": case["split"], "passed": ok, "judge_used": False,
                        "error": detail.get("error"), "detail": detail})
    return results
