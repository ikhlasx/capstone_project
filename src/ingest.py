"""Normalise tickets from any channel into the internal `Ticket` model.

Design rules:
- One bad record never sinks a batch. Records that can be repaired are repaired, and each
  repair is noted in `ingest_warnings`. Records that cannot become a Ticket (for example a bare
  string where an object was expected) go to `IngestResult.errors` with their index.
- Only whole-input problems raise `IngestError`: a missing file, invalid JSON, or a wrong
  top-level shape. The harness reports these and exits cleanly.
- No dataset paths are hardcoded here. Callers pass the path.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import UNKNOWN, Channel, IngestError, IngestResult, RecordError, Ticket

# Alternative field names we accept, mapped to the canonical name. Canonical names come first.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ticket_id": ("ticket_id", "id", "ticketId", "ticket"),
    "channel": ("channel", "source", "origin"),
    "subject": ("subject", "title", "topic"),
    "body": ("body", "message", "text", "content", "comment", "description"),
    "received_at": ("received_at", "created_at", "timestamp", "date", "sent_at"),
    "customer_id": ("customer_id", "customerId", "account_id"),
    "customer_tier": ("customer_tier", "tier", "plan"),
    "customer_region": ("customer_region", "region"),
    "language_fluency": ("language_fluency", "fluency"),
    "labels": ("labels",),
    "history": ("history",),
}

CHANNEL_ALIASES: dict[str, Channel] = {
    "email": Channel.EMAIL, "e_mail": Channel.EMAIL, "mail": Channel.EMAIL,
    "chat": Channel.CHAT, "live_chat": Channel.CHAT, "livechat": Channel.CHAT,
    "docs_comment": Channel.DOCS_COMMENT, "doc_comment": Channel.DOCS_COMMENT,
    "docs": Channel.DOCS_COMMENT, "documentation_comment": Channel.DOCS_COMMENT,
    "forum": Channel.FORUM, "community": Channel.FORUM, "community_forum": Channel.FORUM,
}

_WS = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _slug(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def _pick(record: dict[str, Any], canonical: str) -> Any:
    for name in FIELD_ALIASES[canonical]:
        if name in record and record[name] is not None:
            return record[name]
    return None


def clean_text(value: Any) -> str:
    """Return a trimmed string with normalised whitespace. None becomes an empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [_WS.sub(" ", line).strip() for line in value.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def normalise_channel(raw: Any) -> Channel:
    if raw is None:
        return Channel.UNKNOWN
    return CHANNEL_ALIASES.get(_slug(str(raw)), Channel.UNKNOWN)


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse an ISO-8601 string or a Unix epoch (seconds or ms). The result is always UTC-aware."""
    if raw in (None, ""):
        return None
    try:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            seconds = raw / 1000 if raw > 1e11 else raw
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        text = str(raw).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except (ValueError, OverflowError, OSError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _category(raw: Any) -> str:
    text = clean_text(raw)
    return _slug(text) if text else UNKNOWN


def _synthetic_id(record: dict[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    return f"ANON-{digest[:10]}"


def normalise_record(record: dict[str, Any]) -> Ticket:
    """Turn one raw dict from any channel into a Ticket. Repairs are recorded, never raised."""
    warnings: list[str] = []

    ticket_id = clean_text(_pick(record, "ticket_id"))
    if not ticket_id:
        ticket_id = _synthetic_id(record)
        warnings.append("missing_ticket_id")

    raw_channel = _pick(record, "channel")
    channel = normalise_channel(raw_channel)
    if channel is Channel.UNKNOWN:
        warnings.append(f"unknown_channel:{clean_text(raw_channel) or 'missing'}")

    subject = clean_text(_pick(record, "subject"))
    body = clean_text(_pick(record, "body"))
    if not body:
        warnings.append("empty_body")
    if not body and not subject:
        warnings.append("empty_text")

    raw_ts = _pick(record, "received_at")
    received_at = parse_timestamp(raw_ts)
    if received_at is None:
        warnings.append("missing_received_at" if raw_ts in (None, "") else "bad_received_at")

    fields = {}
    for name in ("customer_tier", "customer_region", "language_fluency"):
        fields[name] = _category(_pick(record, name))
        if fields[name] == UNKNOWN:
            warnings.append(f"missing_{name}")

    labels = _pick(record, "labels")
    history = _pick(record, "history")

    return Ticket(
        ticket_id=ticket_id,
        channel=channel,
        subject=subject,
        body=body,
        received_at=received_at,
        customer_id=clean_text(_pick(record, "customer_id")) or UNKNOWN,
        labels=labels if isinstance(labels, dict) else None,
        history=history if isinstance(history, dict) else None,
        ingest_warnings=tuple(warnings),
        **fields,
    )


def ingest_records(records: Iterable[Any]) -> IngestResult:
    tickets: list[Ticket] = []
    errors: list[RecordError] = []
    seen: dict[str, int] = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(RecordError(index=index, reason=f"expected object, got {type(record).__name__}"))
            continue
        try:
            ticket = normalise_record(record)
        except Exception as exc:  # defensive: a single record must never stop the batch
            errors.append(RecordError(index=index, reason=f"{type(exc).__name__}: {exc}"))
            continue

        # Duplicate ids would break the one-decision-per-ticket reconciliation in the log,
        # so we make them unique and flag the change.
        count = seen.get(ticket.ticket_id, 0) + 1
        seen[ticket.ticket_id] = count
        if count > 1:
            ticket = ticket.model_copy(update={
                "ticket_id": f"{ticket.ticket_id}#{count}",
                "ingest_warnings": ticket.ingest_warnings + ("duplicate_ticket_id",),
            })
        tickets.append(ticket)

    return IngestResult(tickets=tickets, errors=errors)


def _read_records(path: Path) -> list[Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise IngestError(f"input file not found: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise IngestError(f"cannot read {path}: {exc}") from exc

    if path.suffix.lower() == ".jsonl":
        records: list[Any] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Keep the line's position so the error report can point at it.
                records.append(f"<invalid JSON on line {lineno}>")
        return records

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError(f"{path} is not valid JSON: {exc}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("tickets"), list):
            return data["tickets"]
        if any(alias in data for alias in FIELD_ALIASES["body"]):
            return [data]  # a single ticket object
    raise IngestError(f"{path}: expected a list of tickets or an object with a 'tickets' list")


def load_tickets(path: str | Path) -> IngestResult:
    """Load and normalise every ticket in a .json (list or {'tickets': [...]}) or .jsonl file."""
    return ingest_records(_read_records(Path(path)))
