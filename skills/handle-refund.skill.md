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
  - Never refund a digital goods order after the license key has been activated.
provenance:
  - ku: 5aa82dca  source: slack/#support 2026-03-08  span: "btw any refund inside the 30 day window we just auto-approve"
  - ku: aad9d473  source: slack/#support 2026-03-11  span: "Going forward, refunds above $500 require manager sign-off."
  - ku: 334a6fa1  source: notion/Refund Policy 2026-01-15  span: "Never refund an order older than 90 days without manager app"
  - ku: 5c1cfb28  source: notion/Refund Policy 2026-01-15  span: "Never exceed the original charge amount."
  - ku: 9070f5f5  source: notion/Refund Policy 2026-01-15  span: "1. Look up the order by order_id."
  - ku: 602a6355  source: notion/Refund Policy 2026-01-15  span: "2. Verify the purchase date and amount."
  - ku: 73496d32  source: notion/Refund Policy 2026-01-15  span: "3. If eligible, issue the refund via Stripe and update the s"
  - ku: 1855eb30  source: zendesk/support tickets 2026-03-01  span: "Never refund a digital goods order after the license key has"
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
