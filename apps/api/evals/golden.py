"""Golden expectations for the Phase-1 refund slice + metric helpers.

The Brain's quality IS its extraction + routing accuracy, so we measure it:
extraction precision/recall against expected KU statements, and routing accuracy
against labeled tasks.
"""
from __future__ import annotations

# Expected canonical knowledge for the refund capability (substring matchers).
# Each expected item matches if ANY active KU statement contains all of its terms.
EXPECTED_KUS = [
    {"type": "policy_rule", "terms": ["30 day", "auto"]},            # auto-approve window
    {"type": "policy_rule", "terms": ["$500", "manager"]},           # high-value approval
    {"type": "policy_rule", "terms": ["never", "90 days"]},          # age guardrail
    {"type": "policy_rule", "terms": ["never exceed", "original"]},  # amount guardrail
    {"type": "procedure_step", "terms": ["look up the order"]},
    {"type": "procedure_step", "terms": ["stripe"]},
]

# Tasks -> the slug they should route to (routing accuracy).
ROUTING_CASES = [
    ("a customer is angry and wants their money back", "handle-refund"),
    ("please issue a refund for order 123", "handle-refund"),
    ("the buyer is asking for a chargeback reversal", "handle-refund"),
    ("reimburse this customer", "handle-refund"),
]


def extraction_metrics(active_statements: list[tuple[str, str]]) -> dict:
    """active_statements: list of (type, statement). Returns precision/recall/f1."""
    matched = 0
    for exp in EXPECTED_KUS:
        for ku_type, stmt in active_statements:
            low = stmt.lower()
            if ku_type == exp["type"] and all(t.lower() in low for t in exp["terms"]):
                matched += 1
                break
    recall = matched / len(EXPECTED_KUS) if EXPECTED_KUS else 0.0
    # precision proxy: share of active KUs that are "useful" (non-empty, typed)
    useful = sum(1 for t, s in active_statements if s.strip())
    precision = useful / len(active_statements) if active_statements else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "matched": matched}
