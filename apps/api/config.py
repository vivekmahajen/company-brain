"""Central configuration. 12-factor: everything via env, secrets never logged."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # --- Database ---------------------------------------------------------
    # Defaults to a local SQLite file so the demo + evals run with zero infra.
    # In production set DATABASE_URL to a Postgres URL. Railway/Heroku-style
    # `postgres://` and bare `postgresql://` URLs are auto-normalized to the
    # psycopg 3 driver (`postgresql+psycopg://`) below, so you can paste the
    # value Railway gives you verbatim.
    database_url: str = Field(default="sqlite+pysqlite:///./company_brain.db")

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = "postgresql+psycopg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # --- LLM --------------------------------------------------------------
    # "fixture" => deterministic, offline, no key required (default).
    # "anthropic" => real Anthropic API.
    llm_provider: str = Field(default="fixture")
    anthropic_api_key: str | None = Field(default=None)
    model_extract: str = Field(default="claude-opus-4-8")
    model_classify: str = Field(default="claude-haiku-4-5")
    model_compile: str = Field(default="claude-opus-4-8")

    # --- Deploy -----------------------------------------------------------
    # Use native pgvector columns + index (requires the pgvector extension,
    # e.g. Railway's pgvector Postgres template). When false (default), vectors
    # are stored as JSON text and similarity is computed in Python — identical
    # Phase-1 results on ANY Postgres, so deploys never hard-fail on a missing
    # extension. Flip to true once pgvector is available.
    use_pgvector: bool = Field(default=False)
    # Seed the refund demo (run the full pipeline) on startup if the DB is empty.
    seed_on_startup: bool = Field(default=False)
    # Action adapters: "sandbox" simulates side effects; "live" hits real
    # providers (gated; never default). Live requires the relevant provider key
    # and fails closed without it.
    actions_mode: str = Field(default="sandbox")
    stripe_api_key: str | None = Field(default=None)
    # Stripe billing (Phase 6). Webhook signing secret; per-plan price ids are read
    # from env STRIPE_PRICE_<PLAN> (e.g. STRIPE_PRICE_TEAM). Without a key, checkout
    # runs in stub mode (self-serve switch, no charge) so the flow is demoable.
    stripe_webhook_secret: str | None = Field(default=None)
    # Minutes a pending approval stays valid before expiring.
    approval_ttl_minutes: int = Field(default=1440)

    # --- Tenancy ----------------------------------------------------------
    default_org_id: str = Field(default="00000000-0000-0000-0000-000000000001")
    # When True, a request whose tenant can't be resolved (no valid token / org
    # header) is rejected 401 instead of falling back to the default org. Keep
    # False for the single-tenant demo; flip True for a real multi-tenant deploy.
    multi_tenant_strict: bool = Field(default=False)
    # Optional shared secret gating tenant creation (POST /api/orgs). When set,
    # the caller must send it as `X-Admin-Token`. When unset, creation is open
    # (fine for the demo; set it before exposing the product publicly).
    admin_token: str | None = Field(default=None)

    # --- Knowledge thresholds --------------------------------------------
    # Units below this confidence never reach an approved skill (M8 gating).
    confidence_review_threshold: float = Field(default=0.7)
    # Cosine similarity at/above which two KUs are considered duplicates (M3).
    dedup_cosine_threshold: float = Field(default=0.86)
    # Entity-resolution clustering threshold.
    entity_cosine_threshold: float = Field(default=0.82)
    # Skill TTL (days) for time-based staleness (M6).
    skill_ttl_days: int = Field(default=30)

    # --- Secrets / credential vault (Phase 2) -----------------------------
    # Key material for the connector-credential vault. Set in production; a
    # missing value falls back to a non-secret dev key with a loud warning.
    secrets_key: str | None = Field(default=None)
    # Public base URL of this API for OAuth redirects (e.g. https://api.acme.com).
    # Per-provider client id/secret are read from env: OAUTH_<KIND>_CLIENT_ID/SECRET.
    oauth_redirect_base: str | None = Field(default=None)
    # Where to send the user after a successful OAuth connect (the console). When
    # set, the callback 302-redirects here; otherwise it returns JSON.
    oauth_success_redirect: str | None = Field(default=None)

    # --- Paths ------------------------------------------------------------
    skills_dir: str = Field(default="skills")
    fixtures_dir: str = Field(default="fixtures")
    resolver_path: str = Field(default="RESOLVER.md")


@lru_cache
def get_settings() -> Settings:
    return Settings()
