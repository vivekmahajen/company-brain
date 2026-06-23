"""§9: approval gating + policy enforcement at execution, drift detection."""
from sqlalchemy import select

from apps.api.models.tables import ExecutionLog
from apps.api.monitor.drift import list_drift, record_observed_outcome
from apps.api.services.execution import execute_tool


def test_small_refund_executes(seeded, db, org_id):
    res = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "55", "amount": 200}, org_id=org_id)
    assert res["status"] == "executed"


def test_large_refund_requires_approval(seeded, db, org_id):
    res = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "1234", "amount": 620}, org_id=org_id)
    assert res["status"] == "approval_required"
    assert "approval_id" in res
    assert "500" in res["gate_reason"] or "refund_high_value" in res["gate_reason"]


def test_execution_is_logged(seeded, db, org_id):
    execute_tool(db, "handle-refund", "update_support_ticket", {"order_id": "55", "note": "x"}, org_id=org_id)
    logs = db.scalars(select(ExecutionLog).where(ExecutionLog.org_id == org_id)).all()
    assert logs, "executions must be logged"


def test_drift_detection(seeded, db, org_id):
    # An agent that refunded $900 without approval drifts from policy.
    result = record_observed_outcome(
        db,
        org_id=org_id,
        skill_id=None,
        tool_name="stripe_refund",
        inputs={"order_id": "Z9", "amount": 900},
        actual_outcome="executed",
    )
    assert result["drift"] is True
    assert result["violated_rule"] == "refund_high_value"
    assert any(d["log_id"] == result["log_id"] for d in list_drift(db, org_id))
