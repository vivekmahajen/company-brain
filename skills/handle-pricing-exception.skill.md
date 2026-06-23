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
  - ku: 79e6dc56  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts up to 15% are automatically approved."
  - ku: caa7368e  source: notion/Pricing Exception Policy 2026-02-01  span: "Discounts above 20% require manager sign-off."
  - ku: 74032beb  source: notion/Pricing Exception Policy 2026-02-01  span: "Never offer a discount above 40% without VP approval."
  - ku: 8750ee0f  source: notion/Pricing Exception Policy 2026-02-01  span: "1. Look up the account by account_id."
  - ku: 23b18522  source: notion/Pricing Exception Policy 2026-02-01  span: "2. Verify the requested discount_percent."
  - ku: 6db358d8  source: notion/Pricing Exception Policy 2026-02-01  span: "3. If eligible, apply the discount and update the CRM."
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
