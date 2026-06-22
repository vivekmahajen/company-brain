"""Pytest bootstrap: isolated SQLite DB + fixture LLM, seeded once per session."""
from __future__ import annotations

import os
import tempfile

# Must be set BEFORE any apps.api import (engine is built at import time).
_TMP = tempfile.mkdtemp(prefix="brain-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP}/test.db")
os.environ.setdefault("LLM_PROVIDER", "fixture")
os.environ.setdefault("SKILLS_DIR", os.path.join(_TMP, "skills"))
os.environ.setdefault("RESOLVER_PATH", os.path.join(_TMP, "RESOLVER.md"))

import pytest  # noqa: E402

from apps.api.config import get_settings  # noqa: E402
from apps.api.models.db import SessionLocal, init_db  # noqa: E402
from apps.api.services.pipeline import run_full_pipeline  # noqa: E402


@pytest.fixture(scope="session")
def org_id() -> str:
    return get_settings().default_org_id


@pytest.fixture(scope="session")
def seeded(org_id):
    """Run the full pipeline once; yield a report. Tests share the seeded DB."""
    init_db()
    db = SessionLocal()
    try:
        report = run_full_pipeline(db, org_id)
    finally:
        db.close()
    return report


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
