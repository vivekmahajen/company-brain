---
slug: handle-pricing-exception
title: Handle a pricing exception
description: >-
  Decide and apply pricing exceptions and discounts, including approval
  thresholds and deal-desk escalation. Use when a customer asks for a
  discount or special pricing.
version: 1
status: needs_review
inputs:
  - account_id (string, required)
  - discount_percent (number, required)
  - reason (string, optional)
tools:
  - name: apply_discount
    side_effecting: true
    approval_required_when: "discount_percent > 20"
  - name: update_crm
    side_effecting: true
    approval_required_when: "never"
guardrails:
  - Never offer a discount above 40% without VP approval.
  - Never promise custom pricing on a call without deal desk confirmation.
  - Never approve a discount above 50% without CFO sign-off.
provenance:
  - ku: fd0fe297  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts up to 15% are automatically approved."
  - ku: ace9344d  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts above 20% require manager sign-off."
  - ku: f4f7a556  source: notion/Pricing Exception Policy 2026-02-01  span: "Never offer a discount above 40% without VP approval."
  - ku: 9dacdc08  source: notion/Pricing Exception Policy 2026-02-01  span: "1. Look up the account by account_id."
  - ku: 14495049  source: notion/Pricing Exception Policy 2026-02-01  span: "2. Verify the requested discount_percent."
  - ku: 2f4b5cff  source: notion/Pricing Exception Policy 2026-02-01  span: "3. If eligible, apply the discount and update the CRM."
  - ku: 8bf710f9  source: transcript/BigCo pricing discussion 2026-02-09  span: "Never promise custom pricing on a call without deal desk con"
  - ku: b71b21a1  source: gmail/deal-desk@acme.com 2026-02-10  span: "Approved a 15% discount for BigCo."
  - ku: e2a1ad40  source: gmail/deal-desk@acme.com 2026-02-10  span: "Never approve a discount above 50% without CFO sign-off."
  - ku: 26a658c6  source: postgres/pricing & orders DB 2026-01-01  span: "Pricing tier Enterprise is measured as $50 per seat per mont"
  - ku: eab66c61  source: postgres/pricing & orders DB 2026-01-01  span: "Pricing tier Pro is measured as $25 per seat per month."
---

## When to use

Decide and apply pricing exceptions and discounts, including approval thresholds and deal-desk escalation. Use when a customer asks for a discount or special pricing.

## Procedure

1. Look up the account by account_id.
2. Verify the requested discount_percent.
3. If eligible, apply the discount and update the CRM.

## Decision rules

- Discounts up to 15% are automatically approved.
- Discounts above 20% require manager sign-off.
- Approved a 15% discount for BigCo.

## Escalation

Escalate to the owning team with full context.
