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

        report = run_full_pipeline(db, org)
        print("\n[1] PIPELINE REPORT")
        print(json.dumps(report, indent=2, default=str))

        print("\n[2] RESOLVER — 'a customer is angry and wants their money back'")
        routes = resolve_task(db, "a customer is angry and wants their money back", org)
        print(json.dumps(routes, indent=2))

        print("\n[3] COMPILED SKILL — handle-refund.skill.md")
        skill = get_skill(db, "handle-refund", org)
        print(skill["body_md"] if skill else "  (none)")

        print("\n[4] EXECUTION GATING")
        small = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "A1", "amount": 120}, org_id=org)
        big = execute_tool(db, "handle-refund", "stripe_refund", {"order_id": "A2", "amount": 620}, org_id=org)
        print("  $120 refund ->", small["outcome"])
        print("  $620 refund ->", big["outcome"], "| reason:", big.get("reason"))
        print("\nDONE.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
