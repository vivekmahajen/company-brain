"""Phase-1 demo: prove the refund loop end-to-end.

Run from the repo root:   python -m apps.api.demo
"""
from __future__ import annotations

import json

from apps.api.config import get_settings
from apps.api.models.db import SessionLocal, init_db
from apps.api.services.execution import execute_tool, get_skill, resolve_task
from apps.api.services.pipeline import run_full_pipeline


def main() -> None:
    init_db()
    org = get_settings().default_org_id
    db = SessionLocal()
    try:
        print("=" * 70)
        print("COMPANY BRAIN — Phase 1 demo (refund workflow)")
        print("=" * 70)

        from apps.api.services.serving import approve_demo_skills

        report = run_full_pipeline(db, org)
        approve_demo_skills(db, org)  # make skills servable over MCP
        print("\n[1] PIPELINE REPORT")
        print(json.dumps(report, indent=2, default=str))

        print("\n[2] RESOLVER — 'a customer is angry and wants their money back'")
        routes = resolve_task(db, "a customer is angry and wants their money back", org)
        print(json.dumps(routes, indent=2))

        print("\n[3] COMPILED SKILL — handle-refund.skill.md")
        skill = get_skill(db, "handle-refund", org)
        print(skill["body_md"] if skill else "  (none)")

        print("\n[4] GOVERNED EXECUTION (server-side facts + approval gate)")
        small = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "55", "amount": 200}, org_id=org)
        big = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "1234", "amount": 620}, org_id=org)
        print("  order #55  ($200, 12d) ->", small["status"])
        print("  order #1234 ($620, 40d) ->", big["status"], "| gate:", big.get("gate_reason"))
        print("\nDONE.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
