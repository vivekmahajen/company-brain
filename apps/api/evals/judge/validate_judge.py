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
    # --- equivalent paraphrases ---
    {"a": "discounts up to 15% are auto-approved",
     "b": "any discount of 15% or less is approved automatically", "human": True},
    {"a": "page the on-call engineer immediately on a Sev1",
     "b": "for a Sev1, alert on-call right away", "human": True},
    {"a": "look up the order by order_id",
     "b": "fetch the order using its id", "human": True},
    {"a": "discounts above 20% require manager sign-off",
     "b": "a manager must approve any discount over 20%", "human": True},
    {"a": "never offer a discount above 40% without VP approval",
     "b": "discounts beyond 40% need VP sign-off", "human": True},
    {"a": "refunds above $500 require manager sign-off",
     "b": "anything over five hundred dollars needs manager approval", "human": True},
    {"a": "verify the purchase date before refunding",
     "b": "check when it was bought prior to issuing the refund", "human": True},
    {"a": "open an incident channel and post a status update",
     "b": "create an incident channel and share a status post", "human": True},
    {"a": "escalate unresolved cases to #refund-approvals",
     "b": "send anything unresolved to the refund-approvals channel", "human": True},
    {"a": "never deploy during an active Sev1 incident",
     "b": "don't ship code while a Sev1 is ongoing", "human": True},
    {"a": "apply the discount and update the CRM",
     "b": "record the discount in the CRM after applying it", "human": True},
    {"a": "refunds within 30 days are auto-approved",
     "b": "auto-approve refunds requested inside a month of purchase", "human": True},
    # --- hard non-equivalents (near-misses) ---
    {"a": "discounts above 20% require manager sign-off",
     "b": "discounts above 25% require manager sign-off", "human": False},
    {"a": "refunds above $500 require manager sign-off",
     "b": "refunds above $5000 require manager sign-off", "human": False},
    {"a": "refunds within 30 days are auto-approved",
     "b": "refunds within 60 days are auto-approved", "human": False},
    {"a": "page the on-call engineer",
     "b": "email the on-call engineer a summary", "human": False},
    {"a": "never refund more than the original charge",
     "b": "never refund less than the original charge", "human": False},
    {"a": "auto-approve discounts up to 15%",
     "b": "auto-approve discounts up to 50%", "human": False},
    {"a": "escalate to the incident commander",
     "b": "escalate to the refund-approvals channel", "human": False},
    {"a": "classify the severity of the incident",
     "b": "resolve the incident and close the channel", "human": False},
    {"a": "look up the order by order_id",
     "b": "look up the account by account_id", "human": False},
    {"a": "manager sign-off is required",
     "b": "no sign-off is required", "human": False},
    {"a": "refund within 30 days",
     "b": "refund only after 30 days", "human": False},
    {"a": "discounts above 40% need VP approval",
     "b": "discounts above 40% are auto-approved", "human": False},
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
