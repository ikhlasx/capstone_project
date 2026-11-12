"""Decision log (A8, FR-11): one row per pipeline stage per ticket, in SQLite.

The columns follow the Governance Framework minimum record. Nested fields are stored as JSON
text. Rows are only ever inserted, never updated, so the log is an append-only audit trail.
A `run_id` groups the rows written by one harness run so they can be reconciled against the
tickets processed in that run.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Stage = Literal["classification", "routing", "generation", "validation"]
Action = Literal["auto_respond", "escalate", "block", "continue"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id       TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    ticket_id         TEXT NOT NULL,
    stage             TEXT NOT NULL,
    input_summary     TEXT NOT NULL,
    model             TEXT NOT NULL,
    prediction        TEXT NOT NULL,
    alternatives      TEXT NOT NULL,
    sources_used      TEXT NOT NULL,
    threshold_applied TEXT NOT NULL,
    action_taken      TEXT NOT NULL,
    reason            TEXT NOT NULL,
    guardrail_results TEXT NOT NULL,
    prompt_version    TEXT,
    requirement_ids   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_run_stage ON decisions (run_id, stage);
CREATE INDEX IF NOT EXISTS idx_decisions_ticket ON decisions (ticket_id);
"""

JSON_FIELDS = ("model", "prediction", "alternatives", "sources_used", "threshold_applied",
               "guardrail_results", "requirement_ids")


class DecisionRecord(BaseModel):
    ticket_id: str
    stage: Stage
    input_summary: str
    model: dict[str, Any]                        # {"name", "version"}
    prediction: dict[str, Any]                   # {"value", "confidence"}
    alternatives: list[dict[str, Any]] = Field(default_factory=list)   # [{"value", "confidence"}]
    sources_used: list[dict[str, Any]] = Field(default_factory=list)   # [{"doc_id", "score"}]
    threshold_applied: dict[str, Any] = Field(default_factory=dict)
    action_taken: Action
    reason: str
    guardrail_results: dict[str, Any] = Field(default_factory=dict)    # {"pii","grounding","tone","injection"}
    prompt_version: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    decision_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def sqlite_path(database_url: str) -> str:
    """Accepts 'sqlite:///./storage/decisions.db', a plain path, or ':memory:'."""
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///"):]
    if "://" in database_url:
        raise ValueError(f"only sqlite URLs are supported, got: {database_url.split('://')[0]}://…")
    return database_url


class DecisionLog:
    def __init__(self, database_url: str, run_id: str | None = None):
        path = sqlite_path(database_url)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        # The API handles requests on worker threads, so the connection is shared and guarded by a lock.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def log(self, record: DecisionRecord) -> str:
        row = record.model_dump()
        for f in JSON_FIELDS:
            row[f] = json.dumps(row[f], ensure_ascii=False)
        row["run_id"] = self.run_id
        cols = ", ".join(row)
        with self._lock:
            self._conn.execute(f"INSERT INTO decisions ({cols}) VALUES ({', '.join('?' * len(row))})",
                               list(row.values()))
            self._conn.commit()
        return record.decision_id

    def count_by_stage(self, run_id: str | None = None) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT stage, COUNT(*) FROM decisions WHERE run_id = ? GROUP BY stage", (run_id or self.run_id,))
        return dict(cur.fetchall())

    def tickets_by_stage(self, run_id: str | None = None) -> dict[str, int]:
        """Distinct tickets logged per stage; used to reconcile against tickets processed."""
        cur = self._conn.execute(
            "SELECT stage, COUNT(DISTINCT ticket_id) FROM decisions WHERE run_id = ? GROUP BY stage",
            (run_id or self.run_id,))
        return dict(cur.fetchall())

    def for_ticket(self, ticket_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM decisions WHERE ticket_id = ? AND run_id = ? ORDER BY timestamp, rowid",
            (ticket_id, run_id or self.run_id))
        names = [d[0] for d in cur.description]
        rows = []
        for raw in cur.fetchall():
            row = dict(zip(names, raw))
            for f in JSON_FIELDS:
                row[f] = json.loads(row[f])
            rows.append(row)
        return rows

    def close(self) -> None:
        self._conn.close()
