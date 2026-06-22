"""LLM provider interface + token/cost accounting.

Swap providers by changing `LLM_PROVIDER`. Everything downstream depends only on
this interface, so a model swap is one file (`anthropic_client.py`).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    # rough per-model USD per 1M tokens, for cost accounting
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.calls += other.calls
        self.cost_usd += other.cost_usd


@dataclass
class LLMResponse:
    data: dict | list
    raw_text: str = ""
    usage: Usage = field(default_factory=Usage)


class LLMClient(abc.ABC):
    """All extraction/compilation/classification flows through one of these."""

    @abc.abstractmethod
    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        model: str | None = None,
        schema_hint: dict | None = None,
        context: dict | None = None,
    ) -> LLMResponse:
        """Return structured JSON (JSON-mode). Implementations must retry + validate.

        `context` carries structured inputs (e.g. artifact text, ku_type). The real
        client folds them into the prompt; the fixture client reads them directly so
        the offline pipeline is deterministic.
        """

    @abc.abstractmethod
    def classify(self, *, text: str, labels: list[str], model: str | None = None) -> str:
        """Cheap single-label classification (e.g. knowledge-bearing?)."""


def get_llm() -> LLMClient:
    from apps.api.config import get_settings

    provider = get_settings().llm_provider.lower()
    if provider == "anthropic":
        from apps.api.llm.anthropic_client import AnthropicClient

        return AnthropicClient()
    from apps.api.llm.fixture_client import FixtureClient

    return FixtureClient()
