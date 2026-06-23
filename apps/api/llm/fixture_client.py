"""Deterministic, offline LLM stand-in.

Implements a rule-based extractor that produces the same typed knowledge units a
real Claude extraction pass would, for the supported domains. This lets the full
pipeline + eval harness run with no network and no API key, and makes extraction
output reproducible (essential for the §7 determinism guard and CI evals).

When LLM_PROVIDER=anthropic, `anthropic_client.AnthropicClient` is used instead;
both implement the same `LLMClient` interface.
"""
from __future__ import annotations

import re

from apps.api.llm.base import LLMClient, LLMResponse, Usage

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NUM_LIST = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_DOLLAR = re.compile(r"\$\s?(\d[\d,]*)")
_DAYS = re.compile(r"(\d+)\s*[- ]?\s*days?")
_PERCENT = re.compile(r"(\d+)\s*%")


def _amount(text: str) -> int | None:
    m = _DOLLAR.search(text)
    return int(m.group(1).replace(",", "")) if m else None


def _days(text: str) -> int | None:
    m = _DAYS.search(text)
    return int(m.group(1)) if m else None


def _percent(text: str) -> int | None:
    m = _PERCENT.search(text)
    return int(m.group(1)) if m else None


def _segments(text: str) -> list[str]:
    segs: list[str] = []
    for line in text.split("\n"):
        m = _NUM_LIST.match(line)
        if m:
            segs.append(line.strip())
            continue
        for s in _SENT_SPLIT.split(line):
            s = s.strip()
            if s:
                segs.append(s)
    return segs


def _classify_segment(seg: str) -> tuple[str, dict, float] | None:
    """Return (ku_type, payload, confidence) or None if not knowledge-bearing."""
    low = seg.lower()
    amount = _amount(seg)
    days = _days(seg)
    percent = _percent(seg)

    list_m = _NUM_LIST.match(seg)
    if list_m:
        step_text = list_m.group(1)
        return (
            "procedure_step",
            {"action": step_text, "step_number": int(re.match(r"\s*(\d+)", seg).group(1))},
            0.9,
        )

    # Guardrails: "never ..." -> high-importance policy_rule
    if low.startswith("never") or " never " in low:
        payload: dict = {"kind": "guardrail", "constraint": seg}
        if amount is not None:
            payload["amount"] = amount
        if days is not None:
            payload["days"] = days
        if percent is not None:
            payload["percent"] = percent
        return ("policy_rule", payload, 0.92)

    # Glossary: "X means Y" / "X is defined as Y"
    gm = re.search(r"^(.*?)\b(means|is defined as|refers to)\b(.*)$", seg, re.I)
    if gm and len(gm.group(1).split()) <= 5:
        return (
            "glossary_term",
            {"term": gm.group(1).strip(" :"), "definition": gm.group(3).strip(" :")},
            0.8,
        )

    # Metric definitions
    if re.search(r"\b(metric|measured as|calculated as|kpi)\b", low):
        return ("metric_definition", {"definition": seg}, 0.78)

    # Policy rules: approval / refund / requirement language with thresholds
    is_policyish = any(
        k in low
        for k in (
            "approv", "require", "sign-off", "sign off", "must", "auto", "refund",
            "exception", "escalat", "policy", "eligible",
        )
    )
    if is_policyish:
        payload = {}
        if "auto" in low and "approv" in low:
            payload["action"] = "auto_approve"
        elif "manager" in low and ("approv" in low or "sign" in low):
            payload["action"] = "manager_approval"
        elif "escalat" in low:
            payload["action"] = "escalate"
        if amount is not None:
            payload["amount_gt"] = amount if (">" in seg or "above" in low or "over" in low or "exceed" in low) else amount
            payload["amount_threshold"] = amount
        if days is not None:
            payload["days_window"] = days
        if percent is not None:
            payload["percent_threshold"] = percent
        # confidence higher when an explicit threshold is present
        conf = 0.9 if (amount is not None or days is not None or percent is not None) else 0.62
        return ("policy_rule", payload, conf)

    return None


class FixtureClient(LLMClient):
    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        schema_hint: dict | None = None,
        context: dict | None = None,
    ) -> LLMResponse:
        context = context or {}
        task = context.get("task")
        if task == "extract":
            return self._extract(context)
        # Unknown task: return empty structured payload deterministically.
        return LLMResponse(data={}, usage=Usage(calls=1))

    def _extract(self, context: dict) -> LLMResponse:
        text: str = context.get("artifact_text", "")
        units = []
        for seg in _segments(text):
            res = _classify_segment(seg)
            if not res:
                continue
            ku_type, payload, conf = res
            topic = "refund" if "refund" in seg.lower() else context.get("topic")
            units.append(
                {
                    "type": ku_type,
                    "statement": seg,
                    "payload": payload,
                    "quote_span": seg,
                    "confidence": conf,
                    "topic": topic,
                }
            )
        usage = Usage(input_tokens=len(text) // 4, output_tokens=len(units) * 30, calls=1)
        return LLMResponse(data={"units": units}, usage=usage)

    def classify(self, *, text: str, labels: list[str], model: str | None = None) -> str:
        low = text.lower()
        knowledge_markers = (
            "refund", "policy", "approv", "require", "procedure", "step",
            "must", "escalat", "exception", "define", "incident", "pricing",
        )
        is_knowledge = any(m in low for m in knowledge_markers) and len(text.split()) >= 5
        if {"knowledge", "chatter"} <= set(labels):
            return "knowledge" if is_knowledge else "chatter"
        return labels[0] if labels else ""
