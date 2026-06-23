"""Postgres reader (M1) — ingests structured rows (rendered to text via a
per-table template) and schema docs, AND backs live execution-time fact
resolution for the GovernedExecutor (INV-2). READ-ONLY by construction: no write
path exists, and any non-SELECT query is rejected. Unlocks pricing metrics +
glossary, and live refund-gate facts."""
from __future__ import annotations

from datetime import datetime

from apps.api.connectors.base import Connector, NormalizedArtifact, _parse_dt


class ReadOnlyViolation(RuntimeError):
    pass


class PostgresReaderConnector(Connector):
    kind = "postgres"

    def _records(self) -> dict:
        if self.config.get("mode") == "live":  # pragma: no cover - needs a RO DSN
            raise RuntimeError("live Postgres mode requires a READ-ONLY connection string")
        return self._load_fixture("pricing.json")

    # -- read-only guard (D-gotcha): a reader must be incapable of writes -----
    @staticmethod
    def assert_readonly(sql: str) -> None:
        head = sql.strip().split(None, 1)[0].lower() if sql.strip() else ""
        if head not in ("select", "with"):
            raise ReadOnlyViolation(f"Postgres reader rejects non-SELECT query: {head!r}")

    def run_select(self, sql: str, params: dict | None = None):  # pragma: no cover - live only
        self.assert_readonly(sql)
        raise RuntimeError("live query path not configured in fixture mode")

    def discover(self) -> dict:
        d = self._records()
        return {"tables": list(d.get("tables", {}).keys())}

    def pull_acls(self) -> dict:
        # No native doc ACL on a DB → brain grant per source; default-deny.
        return self._native_groups([])

    def pull(self, since: datetime | None = None) -> list[NormalizedArtifact]:
        d = self._records()
        out: list[NormalizedArtifact] = []
        for table, spec in d.get("tables", {}).items():
            if table == "orders":
                continue  # facts, not knowledge artifacts
            template = spec.get("render_template", "{__row__}")
            for row in spec.get("rows", []):
                occ = _parse_dt(row.get("updated_at"))
                if not self._since_ok(since, occ):
                    continue
                text = template.format(**row)
                out.append(NormalizedArtifact(
                    external_id=f"pg-{table}-{row.get('id')}", kind="db_row", content_text=text,
                    author="postgres", occurred_at=occ, raw={"table": table, "row": row}))
            schema_occ = _parse_dt(spec.get("updated_at"))
            if spec.get("schema_doc") and self._since_ok(since, schema_occ):
                out.append(NormalizedArtifact(
                    external_id=f"pg-schema-{table}", kind="db_table_schema",
                    content_text=spec["schema_doc"], author="postgres",
                    occurred_at=schema_occ, raw={"table": table}))
        return out

    # -- execution-time facts (INV-2): live gate facts, not agent claims ------
    def resolve_facts(self, order_id: str) -> dict | None:
        d = self._records()
        for row in d.get("tables", {}).get("orders", {}).get("rows", []):
            if str(row.get("id")) == str(order_id):
                return {"order_id": str(order_id), "amount": row["amount"],
                        "original_charge": row["amount"], "age_days": row.get("age_days", 0)}
        return None
