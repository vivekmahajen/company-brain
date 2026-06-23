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
  - Never deploy code during an active Sev1 incident.
  - Never roll out schema changes during an active incident without a backout plan.
  - Never downgrade incident severity without incident commander sign-off.
  - Never close the incident channel before the post-mortem is published.
provenance:
  - ku: 81ade036  source: notion/Incident Response Runbook 2026-02-10  span: "Never resolve a Sev1 incident without a written post-mortem."
  - ku: 5f903dcf  source: notion/Incident Response Runbook 2026-02-10  span: "1. Classify the severity of the incident."
  - ku: 1dded122  source: notion/Incident Response Runbook 2026-02-10  span: "2. Page the on-call engineer for the affected service."
  - ku: 89e9420b  source: notion/Incident Response Runbook 2026-02-10  span: "3. Open an incident channel and post a status update."
  - ku: 6f33120c  source: github/acme/platform (incidents) 2026-02-12  span: "Never deploy code during an active Sev1 incident."
  - ku: 0e9d068a  source: github/Postmortem: checkout Sev1 outage 2026-02-13  span: "Never roll out schema changes during an active incident with"
  - ku: 7d7b377f  source: linear/Sev1 incident: checkout outage 2026-02-12  span: "Never downgrade incident severity without incident commander"
  - ku: 64bbe901  source: transcript/Checkout Sev1 incident retro 2026-02-14  span: "Never close the incident channel before the post-mortem is p"
---

## When to use

Triage and respond to production incidents: classify severity, page on-call, open an incident channel, and post status updates. Use when a service is down or degraded.

## Procedure

1. Classify the severity of the incident.
2. Page the on-call engineer for the affected service.
3. Open an incident channel and post a status update.

## Escalation

Escalate to the owning team with full context.
