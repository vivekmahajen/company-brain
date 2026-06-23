---
slug: handle-refund
title: Handle a customer refund
description: >-
  Decide and execute customer refunds, including auto-approval thresholds,
  exception handling, and escalation. Use when a customer requests money
  back.
version: 1
status: needs_review
inputs:
  - order_id (string, required)
  - amount (number, required)
  - reason (string, optional)
tools:
  - name: stripe_refund
    side_effecting: true
    approval_required_when: "amount > 500"
  - name: update_support_ticket
    side_effecting: true
    approval_required_when: "never"
guardrails:
  - Never refund an order older than 90 days without manager approval.
  - Never exceed the original charge amount.
provenance:
  - ku: f1f65838  source: slack/#support 2026-03-08  span: "btw any refund inside the 30 day window we just auto-approve"
  - ku: 190582d5  source: slack/#support 2026-03-11  span: "Going forward, refunds above $500 require manager sign-off."
  - ku: d26aa107  source: notion/Refund Policy 2026-01-15  span: "Never refund an order older than 90 days without manager app"
  - ku: 3b478743  source: notion/Refund Policy 2026-01-15  span: "Never exceed the original charge amount."
  - ku: 0735e469  source: notion/Refund Policy 2026-01-15  span: "1. Look up the order by order_id."
  - ku: a9f5558d  source: notion/Refund Policy 2026-01-15  span: "2. Verify the purchase date and amount."
  - ku: 4bd83d68  source: notion/Refund Policy 2026-01-15  span: "3. If eligible, issue the refund via Stripe and update the s"
---

## When to use

A customer is requesting a refund or chargeback reversal.

## Decision procedure

1. Look up the order via `order_id`. If older than 90 days → escalate (guardrail).
2. If `amount <= 500` AND within 30 days of purchase → call `stripe_refund` and `update_support_ticket`.
3. If `amount > 500` → return APPROVAL_REQUIRED with a summary for a manager.
4. If a documented exception applies (see provenance) → follow it and log the rationale.

## Escalation

Route to #refund-approvals; attach order, amount, reason, and policy citation.
