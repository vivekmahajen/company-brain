"""Real Anthropic client. Same interface as FixtureClient.

Uses JSON-mode-style prompting (forced JSON output), retries with backoff, and
token/cost accounting. Selected via LLM_PROVIDER=anthropic. This is the ONE file
to touch to change model behavior.
"""
from __future__ import annotations

import json
import time

from apps.api.config import get_settings
from apps.api.llm.base import LLMClient, LLMResponse, Usage
from apps.api.llm.prompts import EXTRACTION_SYSTEM

# rough public pricing (USD per 1M tokens) for cost accounting
_PRICING = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _cost(model: str, usage) -> float:
    pin, pout = _PRICING.get(model, (0.0, 0.0))
    return usage.input_tokens / 1e6 * pin + usage.output_tokens / 1e6 * pout


class AnthropicClient(LLMClient):
    def __init__(self) -> None:
        from anthropic import Anthropic

        s = get_settings()
        if not s.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        self._client = Anthropic(api_key=s.anthropic_api_key)
        self._s = s

    def _call(self, *, system: str, prompt: str, model: str, max_tokens: int = 4096) -> tuple[str, Usage]:
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                msg = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(b.text for b in msg.content if b.type == "text")
                u = Usage(
                    input_tokens=msg.usage.input_tokens,
                    output_tokens=msg.usage.output_tokens,
                    calls=1,
                )
                u.cost_usd = _cost(model, u)
                return text, u
            except Exception as e:  # noqa: BLE001 - retry transient errors
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Anthropic call failed after retries: {last_err}")

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        schema_hint: dict | None = None,
        context: dict | None = None,
    ) -> LLMResponse:
        model = model or self._s.model_extract
        full = prompt
        if context and context.get("task") == "extract":
            full = (
                f"{EXTRACTION_SYSTEM}\n\nArtifact (occurred_at={context.get('occurred_at')}):\n"
                f'"""\n{context.get("artifact_text", "")}\n"""\n\nReturn JSON only.'
            )
        if schema_hint:
            full += f"\n\nReturn JSON matching this schema:\n{json.dumps(schema_hint)}"
        text, usage = self._call(system=system, prompt=full + "\n\nRespond with JSON only.", model=model)
        data = _parse_json(text)
        return LLMResponse(data=data, raw_text=text, usage=usage)

    def classify(self, *, text: str, labels: list[str], model: str | None = None) -> str:
        model = model or self._s.model_classify
        prompt = (
            f"Classify the following into exactly one of {labels}. Reply with the label only.\n\n{text}"
        )
        out, _ = self._call(system="You are a precise classifier.", prompt=prompt, model=model, max_tokens=16)
        out = out.strip().lower()
        for lbl in labels:
            if lbl in out:
                return lbl
        return labels[0]


def _parse_json(text: str) -> dict | list:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") if "{" in text else text.find("["):]
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1] or [0])
    return json.loads(text[start:])
