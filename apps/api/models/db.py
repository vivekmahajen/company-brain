"""Database engine/session + the pgvector seam.

The embedding column uses real pgvector when the engine is PostgreSQL and a
JSON-encoded fallback on SQLite. This keeps the demo + evals runnable with no
infra while leaving a one-type seam for production pgvector.
"""
from __future__ import annotations

import json
from typing import Iterator

from sqlalchemy import String, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from apps.api.config import get_settings

_settings = get_settings()
_is_sqlite = _settings.database_url.startswith("sqlite")

engine = create_engine(
    _settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class Embedding(TypeDecorator):
    """list[float] <-> pgvector (Postgres) or JSON text (SQLite)."""

    cache_ok = True
    impl = String

    def load_dialect_impl(self, dialect):
        # Native pgvector only when explicitly enabled AND on Postgres; otherwise
        # JSON text, so deploys work on any Postgres without the extension.
        if dialect.name == "postgresql" and get_settings().use_pgvector:
            from pgvector.sqlalchemy import Vector  # imported lazily

            return dialect.type_descriptor(Vector(EMBED_DIM))
        return dialect.type_descriptor(String())

    def _native(self, dialect) -> bool:
        return dialect.name == "postgresql" and get_settings().use_pgvector

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if self._native(dialect):
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if self._native(dialect) and not isinstance(value, str):
            return list(value)
        return json.loads(value)


EMBED_DIM = 256  # fixture embedding dimension; matches llm/embeddings.py


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Enables the pgvector extension only when requested."""
    if not _is_sqlite and get_settings().use_pgvector:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    # Import models so they register on Base.metadata before create_all.
    from apps.api.models import serving, tables  # noqa: F401

    Base.metadata.create_all(engine)
    _ensure_added_columns()


# Columns added after the initial schema. create_all() only creates missing
# *tables*, never alters existing ones, so additive columns are applied here so
# already-deployed databases pick them up without a manual migration.
_ADDED_COLUMNS = {
    "execution_log": {
        "principal_id": "VARCHAR",
        "idempotency_key": "VARCHAR",
        "gate_decision": "VARCHAR",
        "approval_request_id": "VARCHAR",
        "transport": "VARCHAR",
        "trace_id": "VARCHAR",
    },
    "order_record": {
        "provider_charge_id": "VARCHAR",
    },
}


def _ensure_added_columns() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for col, sqltype in cols.items():
                if col not in have:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {sqltype}'))
