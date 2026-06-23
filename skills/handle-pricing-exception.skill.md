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
  - ku: 5329fb4c  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts up to 15% are automatically approved."
  - ku: b874172a  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts above 20% require manager sign-off."
  - ku: 9684b8db  source: notion/Pricing Exception Policy 2026-02-01  span: "Never offer a discount above 40% without VP approval."
  - ku: 4867fb71  source: notion/Pricing Exception Policy 2026-02-01  span: "1. Look up the account by account_id."
  - ku: d0166061  source: notion/Pricing Exception Policy 2026-02-01  span: "2. Verify the requested discount_percent."
  - ku: b854983f  source: notion/Pricing Exception Policy 2026-02-01  span: "3. If eligible, apply the discount and update the CRM."
  - ku: 582aad0e  source: transcript/BigCo pricing discussion 2026-02-09  span: "Never promise custom pricing on a call without deal desk con"
  - ku: 642fed3b  source: gmail/deal-desk@acme.com 2026-02-10  span: "Approved a 15% discount for BigCo."
  - ku: 441b7ad1  source: gmail/deal-desk@acme.com 2026-02-10  span: "Never approve a discount above 50% without CFO sign-off."
  - ku: 1b14034c  source: postgres/pricing & orders DB 2026-01-01  span: "Pricing tier Enterprise is measured as $50 per seat per mont"
  - ku: e93c52e6  source: postgres/pricing & orders DB 2026-01-01  span: "Pricing tier Pro is measured as $25 per seat per month."
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
