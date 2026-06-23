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
provenance:
  - ku: e65206eb  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts up to 15% are automatically approved."
  - ku: 8e34ee50  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts above 20% require manager sign-off."
  - ku: 1112f938  source: notion/Pricing Exception Policy 2026-02-01  span: "Never offer a discount above 40% without VP approval."
  - ku: b62108e0  source: notion/Pricing Exception Policy 2026-02-01  span: "1. Look up the account by account_id."
  - ku: d33740fc  source: notion/Pricing Exception Policy 2026-02-01  span: "2. Verify the requested discount_percent."
  - ku: c381ae6a  source: notion/Pricing Exception Policy 2026-02-01  span: "3. If eligible, apply the discount and update the CRM."
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

## Escalation

Escalate to the owning team with full context.
