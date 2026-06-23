"""Validate the judge against human labels → Cohen's κ (§6, TRUST-5).

A small human-labeled set of (A, B, human_equivalent) pairs. If κ < 0.7, metrics
that depend on the judge are flagged low-trust on the scorecard.
"""
from __future__ import annotations

from apps.api.evals.judge.judge import equivalent

# Human-labeled equivalence pairs (the gold for judging the judge).
HUMAN_PAIRS = [
    {"a": "refunds within 30 days are auto-approved",
     "b": "any refund inside the 30 day window we just auto-approve", "human": True},
    {"a": "refunds above $500 require manager sign-off",
     "b": "refund requests over $500 need a manager to approve", "human": True},
    {"a": "never exceed the original charge amount",
     "b": "do not refund more than what was originally charged", "human": True},
    {"a": "refunds above $500 require manager sign-off",
     "b": "refunds within 30 days are auto-approved", "human": False},
    {"a": "page the on-call engineer",
     "b": "look up the order by order_id", "human": False},
    {"a": "discounts above 20% require manager sign-off",
     "b": "discounts above 40% require VP approval", "human": False},
    {"a": "never refund an order older than 90 days without manager approval",
     "b": "orders older than 90 days need manager approval before refunding", "human": True},
    {"a": "classify the severity of the incident",
     "b": "never resolve a Sev1 without a post-mortem", "human": False},
]


def cohens_kappa() -> dict:
    judge_labels, human_labels = [], []
    for p in HUMAN_PAIRS:
        judge_labels.append(equivalent(p["a"], p["b"])["equivalent"])
        human_labels.append(p["human"])

    n = len(human_labels)
    agree = sum(1 for j, h in zip(judge_labels, human_labels) if j == h)
    po = agree / n
    # expected agreement by chance
    pj_true = sum(judge_labels) / n
    ph_true = sum(human_labels) / n
    pe = pj_true * ph_true + (1 - pj_true) * (1 - ph_true)
    kappa = (po - pe) / (1 - pe) if (1 - pe) else 1.0
    return {"kappa": round(kappa, 3), "observed_agreement": round(po, 3), "n": n,
            "low_trust": kappa < 0.7}
