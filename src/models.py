"""Internal data model shared by every pipeline stage.

Every channel (email, chat, docs_comment, forum) is normalised into one `Ticket`. Fields a
channel does not supply get safe defaults, and anything ingest had to repair is recorded in
`ingest_warnings` so it is visible downstream (and in the decision log) instead of silent.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

UNKNOWN = "unknown"


class Channel(str, Enum):
    EMAIL = "email"
    CHAT = "chat"
    DOCS_COMMENT = "docs_comment"
    FORUM = "forum"
    UNKNOWN = "unknown"  # unrecognised source; still triaged, never dropped


class Ticket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    channel: Channel
    subject: str = ""
    body: str = ""
    received_at: datetime | None = None

    customer_id: str = UNKNOWN
    customer_tier: str = UNKNOWN
    customer_region: str = UNKNOWN
    language_fluency: str = UNKNOWN

    # Evaluation-only payloads from the datasets. The pipeline must never read these when
    # making a decision. Only the harness reads them, to score the results.
    labels: dict[str, Any] | None = None
    history: dict[str, Any] | None = None

    ingest_warnings: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def text(self) -> str:
        """Subject and body as one string, the input for classification and retrieval."""
        return "\n".join(p for p in (self.subject, self.body) if p)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class IngestError(Exception):
    """The input as a whole cannot be read (missing file, not JSON, wrong top-level shape)."""


class RecordError(BaseModel):
    """One record that could not become a Ticket at all. The rest of the batch still loads."""

    index: int
    reason: str


class IngestResult(BaseModel):
    tickets: list[Ticket]
    errors: list[RecordError] = Field(default_factory=list)
