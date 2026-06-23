"""E3 — Compilation fidelity + determinism on the REAL compiler.

Asserts the compiled skill contains the required rules/bindings/guardrails
(structural, not exact text) and that recompiling identical KUs yields an
identical version (determinism = 1.0, a hard gate).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.compiler.skill_compiler import compile_skill
from apps.api.evals.loader import load_cases
from apps.api.evals.runners.harness import EVAL_ORG
from apps.api.services.execution import get_skill


def _check(db: Session, case: dict) -> tuple[bool, dict]:
    skill = get_skill(db, case["slug"], EVAL_ORG)
    if not skill:
        return False, {"detail": "skill not found"}
    exp = case["expected_skill"]
    body = skill["body_md"].lower()
    detail = {"missing": []}

    for s in exp.get("must_contain_body", []):
        if s.lower() not in body:
            detail["missing"].append(f"body:{s}")
    bindings = {t["name"]: t for t in skill["tools"]}
    for b in exp.get("must_contain_bindings", []):
        tb = bindings.get(b["name"])
        if not tb:
            detail["missing"].append(f"binding:{b['name']}")
            continue
        if b.get("side_effecting") is not None and tb["side_effecting"] != b["side_effecting"]:
            detail["missing"].append(f"binding-se:{b['name']}")
        if b.get("approval_when_contains") and b["approval_when_contains"] not in (tb.get("approval_expression") or ""):
            detail["missing"].append(f"binding-approval:{b['name']}")
    guardrails = " ".join(skill["frontmatter"].get("guardrails", [])).lower()
    for g in exp.get("must_contain_guardrails", []):
        if g.lower() not in guardrails:
            detail["missing"].append(f"guardrail:{g}")
    if len(skill.get("provenance", [])) < exp.get("min_provenance", 0):
        detail["missing"].append("provenance")

    determinism_ok = True
    if exp.get("determinism"):
        v1 = compile_skill(db, EVAL_ORG, case["topic"])
        v2 = compile_skill(db, EVAL_ORG, case["topic"])
        determinism_ok = (v1.version == v2.version and v1.content_signature == v2.content_signature)
        detail["determinism"] = determinism_ok

    ok = not detail["missing"] and determinism_ok
    return ok, detail


def run(db: Session, split: str | None = "test") -> list[dict]:
    results = []
    for case in load_cases("compilation", split):
        try:
            ok, detail = _check(db, case)
            results.append({
                "stage": "compilation", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": ok, "judge_used": False, "error": None, "detail": detail,
            })
        except Exception as e:  # noqa: BLE001 - fail closed
            results.append({
                "stage": "compilation", "case_id": case["id"], "tier": case["tier"], "split": case["split"],
                "passed": False, "judge_used": False, "error": f"{type(e).__name__}: {e}", "detail": {},
            })
    return results
