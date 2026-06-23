"""GovernedExecutor — the single choke point for every tool side effect (INV-1).

Every invocation (core, skill-bound, stdio, HTTP, REST) runs `invoke()` and the
§6 pipeline. No other code path performs a side effect. The per-skill MCP
wrappers and the REST /execute endpoint are thin callers of this module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.actions.registry import get_action
from apps.api.auth.principals import has_scope
from apps.api.config import get_settings
from apps.api.execution.facts import resolve_facts
from apps.api.execution.gates import evaluate_guardrails, safe_eval
from apps.api.execution.idempotency import find_completed, find_pending_approval
from apps.api.models.serving import ApprovalRequest, Principal
from apps.api.models.tables import ExecutionLog, Skill, SkillBinding


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- result builders ------------------------------------------------------
def _executed(result: dict, execution_id: str) -> dict:
    return {"status": "executed", "result": result, "execution_id": execution_id}


def _approval_required(ar: ApprovalRequest) -> dict:
    f = ar.resolved_facts_jsonb or {}
    return {
        "status": "approval_required",
        "approval_id": ar.id,
        "summary": f"{ar.tool_name} on order {f.get('order_id', '?')} "
        f"(charge {f.get('original_charge', '?')})",
        "what_will_happen": f"{ar.tool_name} with {ar.input_jsonb}",
        "gate_reason": ar.gate_reason,
    }


def _denied(reason: str, detail: str) -> dict:
    return {"status": "denied", "reason": reason, "detail": detail}


def _replay(result: dict) -> dict:
    return {"status": "idempotent_replay", "result": result}


class GovernedExecutor:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- helpers ------------------------------------------------------------
    def _latest_approved_skill(self, org_id: str, slug: str) -> Skill | None:
        return self.db.scalars(
            select(Skill)
            .where(Skill.org_id == org_id, Skill.slug == slug, Skill.status == "approved")
            .order_by(Skill.version.desc())
        ).first()

    def _log(self, **kw) -> ExecutionLog:
        row = ExecutionLog(**kw)
        self.db.add(row)
        self.db.flush()
        return row

    # -- the choke point ----------------------------------------------------
    def invoke(
        self,
        *,
        principal: Principal,
        skill_slug: str,
        tool_name: str,
        args: dict,
        idempotency_key: str,
        approval_id: str | None = None,
        transport: str = "api",
        trace_id: str | None = None,
    ) -> dict:
        db = self.db
        org = principal.org_id
        trace_id = trace_id or str(uuid.uuid4())
        log_base = dict(
            org_id=org,
            principal_id=principal.id,
            agent_id=principal.display_name,
            idempotency_key=idempotency_key,
            transport=transport,
            trace_id=trace_id,
            input_jsonb={"tool": tool_name, "skill": skill_slug, **args},
        )

        # 2. AUTHORIZE -----------------------------------------------------
        skill = self._latest_approved_skill(org, skill_slug)
        if not skill:
            self._log(outcome="denied_permission", gate_decision="not_visible",
                      output_jsonb={"reason": "skill not found or not visible"}, **log_base)
            db.commit()
            return _denied("denied_permission", f"skill '{skill_slug}' not found or not approved")
        binding = db.scalar(
            select(SkillBinding).where(SkillBinding.skill_id == skill.id, SkillBinding.tool_name == tool_name)
        )
        if not binding:
            self._log(skill_id=skill.id, outcome="error",
                      output_jsonb={"reason": "tool not bound"}, **log_base)
            db.commit()
            return _denied("error", f"tool '{tool_name}' not bound to '{skill_slug}'")

        log_base["skill_id"] = skill.id

        # Visibility check BEFORE any fact lookup (VIS-2; hidden == not found).
        from apps.api.access.visibility import VisibilityFilter

        if not VisibilityFilter(db, principal).visible("skill", skill.id, action="invoke"):
            self._log(outcome="denied_permission", gate_decision="not_visible", **log_base)
            db.commit()
            return _denied("denied_permission", "skill not found or not visible")

        if binding.side_effecting and not has_scope(principal, f"invoke:{tool_name}"):
            self._log(outcome="denied_permission", gate_decision="missing_scope", **log_base)
            db.commit()
            return _denied("denied_permission", f"principal lacks invoke:{tool_name}")

        # 3. IDEMPOTENCY ---------------------------------------------------
        done = find_completed(db, org, idempotency_key)
        if done:
            self._log(outcome="idempotent_replay", gate_decision="replay",
                      approval_request_id=done.approval_request_id,
                      output_jsonb=done.output_jsonb, **log_base)
            db.commit()
            return _replay((done.output_jsonb or {}).get("result", done.output_jsonb))

        # 4. RESOLVE FACTS (server truth) ----------------------------------
        facts = resolve_facts(db, org, tool_name, args)

        # 5. GUARDRAILS ----------------------------------------------------
        hard, soft = evaluate_guardrails(tool_name, facts)
        if hard:
            self._log(outcome="denied_guardrail", gate_decision=f"guardrail:{hard}",
                      output_jsonb={"reason": hard}, **log_base)
            db.commit()
            return _denied("denied_guardrail", hard)

        # 6. APPROVAL GATE -------------------------------------------------
        if approval_id:
            ar = db.get(ApprovalRequest, approval_id)
            err = self._validate_approval(ar, principal, idempotency_key, tool_name)
            if err:
                self._log(outcome="error", gate_decision="bad_approval",
                          output_jsonb={"reason": err}, **log_base)
                db.commit()
                return _denied("error", err)
            # Anti param-swap: execute EXACTLY the approved request, never the
            # args the caller re-sends with the approval id.
            approved_args = ar.input_jsonb
            approved_facts = resolve_facts(db, org, tool_name, approved_args)
            return self._perform(principal, skill, binding, tool_name, approved_args, approved_facts,
                                 idempotency_key, transport, trace_id, approval_request=ar,
                                 gate_decision="approved")

        gate_trip = False
        reason = ""
        if binding.approval_required and safe_eval(binding.approval_expression or "never", facts):
            gate_trip = True
            reason = f"{binding.approval_expression} on resolved facts"
        if soft:
            gate_trip = True
            reason = (reason + "; " if reason else "") + soft
        # M8 policy rows, evaluated against SERVER facts (INV-2).
        from apps.api.governance.policy import check_policies

        pol = check_policies(db, org, tool_name, facts)
        if not pol["allowed"]:
            gate_trip = True
            reason = (reason + "; " if reason else "") + f"policy {pol['rule']}"

        if gate_trip:
            ar = find_pending_approval(db, org, idempotency_key)
            if not ar:
                ttl = timedelta(minutes=get_settings().approval_ttl_minutes)
                ar = ApprovalRequest(
                    org_id=org, skill_id=skill.id, binding_id=binding.id, tool_name=tool_name,
                    requested_by_principal=principal.id, input_jsonb=dict(args),
                    resolved_facts_jsonb=facts, gate_reason=reason, status="pending",
                    idempotency_key=idempotency_key, expires_at=_now() + ttl,
                )
                db.add(ar)
                db.flush()
            self._log(outcome="approval_required", gate_decision=f"gate:{reason}",
                      approval_request_id=ar.id, output_jsonb=_approval_required(ar), **log_base)
            db.commit()
            return _approval_required(ar)

        # 7. EXECUTE (no gate) ---------------------------------------------
        return self._perform(principal, skill, binding, tool_name, args, facts,
                             idempotency_key, transport, trace_id, gate_decision="passed")

    # -- approval validation (INV-4) ---------------------------------------
    def _validate_approval(self, ar, principal, key, tool_name) -> str | None:
        if not ar:
            return "approval not found"
        if ar.status == "executed":
            return None  # will replay via idempotency on _perform
        if ar.status != "approved":
            return f"approval is '{ar.status}', not approved"
        if ar.idempotency_key != key:
            return "idempotency_key mismatch with approval"
        if ar.tool_name != tool_name:
            return "tool mismatch with approval"
        if ar.requested_by_principal == principal.id and principal.role != "approver":
            return "requester cannot resume without approver authority"
        return None

    # -- execution + logging (the only place an adapter runs) --------------
    def _perform(self, principal, skill, binding, tool_name, args, facts, key,
                 transport, trace_id, *, approval_request=None, gate_decision="passed") -> dict:
        db = self.db
        # Idempotent replay if the held action already executed.
        if approval_request and approval_request.status == "executed":
            return _replay(approval_request.result_jsonb)

        action = get_action(tool_name)
        try:
            result = action.execute(args, facts, key)
        except Exception as e:  # noqa: BLE001 - adapter/provider failure must not crash the server
            self._log(
                org_id=principal.org_id, principal_id=principal.id, skill_id=skill.id,
                idempotency_key=key, transport=transport, trace_id=trace_id,
                input_jsonb={"tool": tool_name, "skill": skill.slug, **args},
                output_jsonb={"error": str(e)}, outcome="error", gate_decision=gate_decision,
                approval_request_id=approval_request.id if approval_request else None,
            )
            db.commit()
            return _denied("error", f"action '{tool_name}' failed: {e}")

        log = self._log(
            org_id=principal.org_id, principal_id=principal.id, agent_id=principal.display_name,
            skill_id=skill.id, idempotency_key=key, transport=transport, trace_id=trace_id,
            input_jsonb={"tool": tool_name, "skill": skill.slug, **args},
            output_jsonb={"result": result}, outcome="executed",
            gate_decision=gate_decision,
            approval_request_id=approval_request.id if approval_request else None,
        )
        if approval_request:
            approval_request.status = "executed"
            approval_request.executed_at = _now()
            approval_request.result_jsonb = result
        db.commit()
        return _executed(result, log.id)

    # -- path (a): server executes a held action on approval ---------------
    def execute_held(self, ar: ApprovalRequest, approver: Principal, transport: str = "console") -> dict:
        skill = self.db.get(Skill, ar.skill_id)
        binding = self.db.get(SkillBinding, ar.binding_id)
        # Re-resolve facts at execution time (truth may have changed); fall back
        # to the snapshot captured at request time.
        facts = ar.resolved_facts_jsonb or resolve_facts(self.db, ar.org_id, ar.tool_name, ar.input_jsonb)
        return self._perform(approver, skill, binding, ar.tool_name, ar.input_jsonb, facts,
                             ar.idempotency_key, transport, str(uuid.uuid4()),
                             approval_request=ar, gate_decision="approved")
