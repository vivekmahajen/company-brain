"""M4 — Skills compiler.

Compile canonical, APPROVED knowledge units for a capability into an executable
SKILL.md (thresholds, tool bindings, guardrails, provenance footnotes).

Guarantees:
  - Confidence gating: only `approved` KUs become skill rules (M8).
  - Side-effecting safety: a skill with any side-effecting tool lands as
    `needs_review`, never auto-approved (per build-prompt guardrail).
  - Determinism: same approved KUs => same `content_signature` => no new version
    (§7 determinism guard). Any change bumps `version`.
"""
from __future__ import annotations

import hashlib
import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.compiler.render import render_skill_md
from apps.api.compiler.templates import SKILL_TEMPLATES
from apps.api.config import get_settings
from apps.api.models.tables import (
    Artifact,
    KnowledgeUnit,
    KUProvenance,
    Skill,
    SkillBinding,
    Source,
)


def _active_approved_kus(db: Session, org_id: str, topic: str) -> list[KnowledgeUnit]:
    kus = db.scalars(
        select(KnowledgeUnit).where(
            KnowledgeUnit.org_id == org_id,
            KnowledgeUnit.topic == topic,
            KnowledgeUnit.status == "approved",
            KnowledgeUnit.valid_to.is_(None),
        )
    ).all()
    return list(kus)


def _signature(kus: list[KnowledgeUnit]) -> str:
    parts = sorted(
        f"{k.type}|{k.statement}|{json.dumps(k.payload_jsonb, sort_keys=True)}" for k in kus
    )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _provenance_footnotes(db: Session, kus: list[KnowledgeUnit]) -> list[dict]:
    foot = []
    for ku in kus:
        prov = db.scalars(
            select(KUProvenance).where(KUProvenance.knowledge_unit_id == ku.id)
        ).first()
        if not prov:
            continue
        art = db.get(Artifact, prov.artifact_id)
        src = db.get(Source, art.source_id) if art else None
        when = art.occurred_at.date().isoformat() if art and art.occurred_at else ""
        label = f"{src.kind}/{(art.raw_jsonb.get('channel') or art.raw_jsonb.get('title') or src.name)}" if src else "?"
        foot.append(
            {
                "ku": ku.id[:8],
                "source": f"{label} {when}".strip(),
                "span": (prov.quote_span or ku.statement)[:60],
            }
        )
    return foot


def _find(kus, type_, action=None, kind=None):
    out = []
    for k in kus:
        if k.type != type_:
            continue
        p = k.payload_jsonb or {}
        if action and p.get("action") != action:
            continue
        if kind and p.get("kind") != kind:
            continue
        out.append(k)
    return out


def _amount(ku) -> int | None:
    p = ku.payload_jsonb or {}
    return p.get("amount_threshold", p.get("amount_gt", p.get("amount")))


def _days(ku) -> int | None:
    p = ku.payload_jsonb or {}
    return p.get("days_window", p.get("days"))


def _percent(ku) -> int | None:
    p = ku.payload_jsonb or {}
    return p.get("percent_threshold", p.get("percent"))


def _threshold_for(kus, action: str, kind: str) -> int | None:
    """First threshold of `kind` (amount|percent|days) on a rule with `action`."""
    getter = {"amount": _amount, "percent": _percent, "days": _days}.get(kind, _amount)
    for k in _find(kus, "policy_rule", action=action):
        v = getter(k)
        if v is not None:
            return v
    return None


def compile_skill(db: Session, org_id: str, topic: str) -> Skill | None:
    tmpl = SKILL_TEMPLATES.get(topic)
    if not tmpl:
        return None
    kus = _active_approved_kus(db, org_id, topic)
    if not kus:
        return None

    signature = _signature(kus)
    latest = db.scalars(
        select(Skill)
        .where(Skill.org_id == org_id, Skill.slug == tmpl["slug"])
        .order_by(Skill.version.desc())
    ).first()
    # Determinism guard: unchanged approved KUs => no new version.
    if latest and latest.content_signature == signature:
        return latest

    # --- derive thresholds from canonical KUs ----------------------------
    auto = _find(kus, "policy_rule", action="auto_approve")
    guardrail_kus = _find(kus, "policy_rule", kind="guardrail")
    policy_rules = _find(kus, "policy_rule")
    steps = sorted(_find(kus, "procedure_step"), key=lambda k: (k.payload_jsonb or {}).get("step_number", 99))

    approval_amount = next((_amount(k) for k in _find(kus, "policy_rule", action="manager_approval") if _amount(k)), None)
    auto_days = next((_days(k) for k in auto if _days(k)), None)
    guardrails = [(k.payload_jsonb or {}).get("constraint", k.statement) for k in guardrail_kus]

    # --- tool bindings (fill approval expressions from thresholds) -------
    fm_tools = []
    bindings_spec = []
    for t in tmpl["tools"]:
        approval_expr = "never"
        approval_required = False
        action = t.get("approval_for_action")
        if action:
            kind = t.get("threshold_kind", "amount")
            field = t.get("approval_field", "amount")
            thr = _threshold_for(kus, action, kind)
            if thr is not None:
                approval_expr = f"{field} > {thr}"
                approval_required = True
        fm_tools.append(
            {
                "name": t["name"],
                "side_effecting": t["side_effecting"],
                "approval_required_when": approval_expr,
            }
        )
        bindings_spec.append(
            {
                "tool_name": t["name"],
                "tool_schema_jsonb": t.get("schema", {}),
                "side_effecting": t["side_effecting"],
                "approval_required": approval_required,
                "approval_expression": approval_expr if approval_required else None,
            }
        )

    provenance = _provenance_footnotes(db, kus)

    # --- body: executable decision procedure ----------------------------
    body = _render_body(topic, tmpl, approval_amount, auto_days, steps, guardrails, policy_rules)

    has_side_effects = any(t["side_effecting"] for t in fm_tools)
    # Side-effecting skills never auto-approve.
    status = "needs_review" if has_side_effects else "approved"

    version = (latest.version + 1) if latest else 1
    frontmatter = {
        "slug": tmpl["slug"],
        "title": tmpl["title"],
        "description": tmpl["description"],
        "version": version,
        "status": status,
        "inputs": tmpl["inputs"],
        "tools": fm_tools,
        "guardrails": guardrails,
        "provenance": provenance,
    }
    body_md = render_skill_md(frontmatter, body)

    skill = Skill(
        org_id=org_id,
        slug=tmpl["slug"],
        title=tmpl["title"],
        summary=tmpl["description"],
        body_md=body_md,
        frontmatter_jsonb=frontmatter,
        version=version,
        status=status,
        source_ku_ids_jsonb=[k.id for k in kus],
        content_signature=signature,
    )
    db.add(skill)
    db.flush()
    for b in bindings_spec:
        db.add(SkillBinding(skill_id=skill.id, **b))
    db.flush()

    _write_skill_file(tmpl["slug"], body_md)
    db.commit()
    return skill


def _render_body(topic, tmpl, approval_amount, auto_days, steps, guardrails, policy_rules) -> str:
    if topic == "refund":
        amt = approval_amount or 500
        days = auto_days or 30
        proc = [
            "1. Look up the order via `order_id`. If older than 90 days → escalate (guardrail).",
            f"2. If `amount <= {amt}` AND within {days} days of purchase → call `stripe_refund` and `update_support_ticket`.",
            f"3. If `amount > {amt}` → return APPROVAL_REQUIRED with a summary for a manager.",
            "4. If a documented exception applies (see provenance) → follow it and log the rationale.",
        ]
        return "\n".join(
            [
                "## When to use",
                "",
                "A customer is requesting a refund or chargeback reversal.",
                "",
                "## Decision procedure",
                "",
                *proc,
                "",
                "## Escalation",
                "",
                "Route to #refund-approvals; attach order, amount, reason, and policy citation.",
            ]
        )

    # Generic, capability-agnostic body built from the extracted KUs.
    lines = ["## When to use", "", tmpl["description"], ""]
    if steps:
        lines += ["## Procedure", ""]
        for i, s in enumerate(steps, 1):
            lines.append(f"{i}. {(s.payload_jsonb or {}).get('action', s.statement)}")
        lines.append("")

    decision = [r for r in policy_rules if (r.payload_jsonb or {}).get("kind") != "guardrail"
                and (r.payload_jsonb or {}).get("action") != "escalate"]
    if decision:
        lines += ["## Decision rules", ""]
        for r in decision:
            lines.append(f"- {r.statement}")
        lines.append("")

    escalations = [r.statement for r in policy_rules if (r.payload_jsonb or {}).get("action") == "escalate"]
    lines += ["## Escalation", "", (escalations[0] if escalations else "Escalate to the owning team with full context.")]
    return "\n".join(lines)


def _write_skill_file(slug: str, body_md: str) -> str:
    settings = get_settings()
    os.makedirs(settings.skills_dir, exist_ok=True)
    path = os.path.join(settings.skills_dir, f"{slug}.skill.md")
    with open(path, "w") as f:
        f.write(body_md)
    return path
