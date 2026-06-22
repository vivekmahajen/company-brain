"""M9 — Closed-loop monitoring.

Compare what happened (execution_log) to what policy says should have happened;
flag drift. Also: promote a real-world decision into a knowledge unit so the
Brain learns from outcomes (the closed loop).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.governance.policy import check_policies
from apps.api.llm.embeddings import embed
from apps.api.models.tables import ExecutionLog, KnowledgeUnit


def record_observed_outcome(
    db: Session,
    *,
    org_id: str,
    skill_id: str | None,
    tool_name: str,
    inputs: dict,
    actual_outcome: str,
    agent_id: str = "external",
) -> dict:
    """Log a real-world outcome and flag drift vs the policy-expected decision."""
    policy = check_policies(db, org_id, tool_name, inputs)
    expected = "approval_required" if not policy["allowed"] else "executed"
    drift = actual_outcome != expected
    log = ExecutionLog(
        org_id=org_id,
        skill_id=skill_id,
        agent_id=agent_id,
        input_jsonb={"tool": tool_name, **inputs},
        output_jsonb={"outcome": actual_outcome},
        outcome=actual_outcome,
        expected_jsonb={"decision": expected, "policy_rule": policy["rule"]},
        drift_flag=drift,
    )
    db.add(log)
    db.commit()
    return {
        "drift": drift,
        "expected": expected,
        "actual": actual_outcome,
        "violated_rule": policy["rule"] if drift else None,
        "log_id": log.id,
    }


def list_drift(db: Session, org_id: str | None = None) -> list[dict]:
    org_id = org_id or get_settings().default_org_id
    rows = db.scalars(
        select(ExecutionLog).where(ExecutionLog.org_id == org_id, ExecutionLog.drift_flag.is_(True))
    ).all()
    return [
        {
            "log_id": r.id,
            "skill_id": r.skill_id,
            "input": r.input_jsonb,
            "expected": r.expected_jsonb,
            "actual": r.outcome,
            "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
        }
        for r in rows
    ]


def promote_outcome_to_ku(db: Session, org_id: str, log_id: str, statement: str) -> KnowledgeUnit:
    """Turn a real-world decision into a (needs_review) knowledge unit."""
    ku = KnowledgeUnit(
        org_id=org_id,
        type="policy_rule",
        statement=statement,
        payload_jsonb={"origin": "observed_outcome", "log_id": log_id},
        embedding=embed(statement),
        confidence=0.6,
        status="needs_review",
        topic="refund",
    )
    db.add(ku)
    db.commit()
    return ku
