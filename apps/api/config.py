"""Central configuration. 12-factor: everything via env, secrets never logged."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # --- Database ---------------------------------------------------------
    # Defaults to a local SQLite file so the demo + evals run with zero infra.
    # In production set DATABASE_URL to postgresql+psycopg://... (pgvector).
    database_url: str = Field(default="sqlite+pysqlite:///./company_brain.db")

    # --- LLM --------------------------------------------------------------
    # "fixture" => deterministic, offline, no key required (default).
    # "anthropic" => real Anthropic API.
    llm_provider: str = Field(default="fixture")
    anthropic_api_key: str | None = Field(default=None)
    model_extract: str = Field(default="claude-opus-4-8")
    model_classify: str = Field(default="claude-haiku-4-5")
    model_compile: str = Field(default="claude-opus-4-8")

    # --- Tenancy ----------------------------------------------------------
    default_org_id: str = Field(default="00000000-0000-0000-0000-000000000001")

    # --- Knowledge thresholds --------------------------------------------
    # Units below this confidence never reach an approved skill (M8 gating).
    confidence_review_threshold: float = Field(default=0.7)
    # Cosine similarity at/above which two KUs are considered duplicates (M3).
    dedup_cosine_threshold: float = Field(default=0.86)
    # Entity-resolution clustering threshold.
    entity_cosine_threshold: float = Field(default=0.82)
    # Skill TTL (days) for time-based staleness (M6).
    skill_ttl_days: int = Field(default=30)

    # --- Paths ------------------------------------------------------------
    skills_dir: str = Field(default="skills")
    fixtures_dir: str = Field(default="fixtures")
    resolver_path: str = Field(default="RESOLVER.md")


@lru_cache
def get_settings() -> Settings:
    return Settings()
