---
slug: respond-to-incident
title: Respond to a production incident
description: >-
  Triage and respond to production incidents: classify severity, page
  on-call, open an incident channel, and post status updates. Use when a
  service is down or degraded.
version: 1
status: needs_review
inputs:
  - service (string, required)
  - severity (string, required)
  - summary (string, optional)
tools:
  - name: page_oncall
    side_effecting: true
    approval_required_when: "never"
  - name: open_incident_channel
    side_effecting: true
    approval_required_when: "never"
  - name: post_status_update
    side_effecting: true
    approval_required_when: "never"
guardrails:
  - Never resolve a Sev1 incident without a written post-mortem.
provenance:
  - ku: 3ccc3945  source: notion/Incident Response Runbook 2026-02-10  span: "Never resolve a Sev1 incident without a written post-mortem."
  - ku: 0cced9cf  source: notion/Incident Response Runbook 2026-02-10  span: "1. Classify the severity of the incident."
  - ku: 778574a3  source: notion/Incident Response Runbook 2026-02-10  span: "2. Page the on-call engineer for the affected service."
  - ku: 0d55eb91  source: notion/Incident Response Runbook 2026-02-10  span: "3. Open an incident channel and post a status update."
---

## When to use

Triage and respond to production incidents: classify severity, page on-call, open an incident channel, and post status updates. Use when a service is down or degraded.

## Procedure

1. Classify the severity of the incident.
2. Page the on-call engineer for the affected service.
3. Open an incident channel and post a status update.

## Escalation

Escalate to the owning team with full context.
