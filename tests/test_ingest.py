"""Tests for src/ingest.py: one real ticket per channel, plus tolerance for messy input."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.ingest import (
    clean_text,
    ingest_records,
    load_tickets,
    normalise_channel,
    normalise_record,
    parse_timestamp,
)
from src.models import UNKNOWN, Channel, IngestError, Ticket

DATA = Path(__file__).resolve().parent.parent / "data"


# --- one real ticket per channel (verbatim shape from the course datasets) -----------------

CHANNEL_SAMPLES = {
    "email": {
        "ticket_id": "T-EMAIL", "channel": "email",
        "subject": "Key stopped working overnight",
        "body": "One of our engineers pushed a key to a public repository by mistake.",
        "received_at": "2026-03-02T08:32:00Z", "customer_id": "CUST-1",
        "customer_tier": "business", "customer_region": "asia_pacific",
        "language_fluency": "fluent",
        "labels": {"intent": "api_key_issue"}, "history": {"escalated": False},
    },
    "chat": {
        "ticket_id": "T-CHAT", "channel": "chat", "subject": "",
        "body": "Every deployment fails at the health check stage.",
        "received_at": "2026-05-23T22:43:00Z", "customer_id": "CUST-2",
        "customer_tier": "standard", "customer_region": "latin_america",
        "language_fluency": "non_fluent",
    },
    "docs_comment": {
        "ticket_id": "T-DOCS", "channel": "docs_comment",
        "subject": "Duplicate webhook deliveries",
        "body": "We are receiving the same event several times.",
        "received_at": "2026-04-10T12:00:00Z", "customer_id": "CUST-3",
        "customer_tier": "enterprise", "customer_region": "europe",
        "language_fluency": "fluent",
    },
    "forum": {
        "ticket_id": "T-FORUM", "channel": "forum",
        "subject": "p95 latency is very high",
        "body": "Our response times have roughly doubled since two days ago.",
        "received_at": "2026-01-15T07:05:00Z", "customer_id": "CUST-4",
        "customer_tier": "standard", "customer_region": "north_america",
        "language_fluency": "fluent",
    },
}


@pytest.mark.parametrize("channel", list(CHANNEL_SAMPLES))
def test_each_channel_maps_to_one_ticket_model(channel):
    raw = CHANNEL_SAMPLES[channel]
    t = normalise_record(raw)
    assert isinstance(t, Ticket)
    assert t.channel is Channel(channel)
    assert t.ticket_id == raw["ticket_id"]
    assert t.body == raw["body"]
    assert t.subject == raw["subject"]
    assert t.customer_tier == raw["customer_tier"]
    assert t.customer_region == raw["customer_region"]
    assert t.language_fluency == raw["language_fluency"]
    assert t.received_at is not None and t.received_at.tzinfo is not None
    assert t.ingest_warnings == ()


def test_chat_has_no_subject_and_text_is_body_only():
    t = normalise_record(CHANNEL_SAMPLES["chat"])
    assert t.subject == ""
    assert t.text == t.body


def test_text_joins_subject_and_body():
    t = normalise_record(CHANNEL_SAMPLES["email"])
    assert t.text == f"{t.subject}\n{t.body}"


def test_eval_payloads_carried_but_optional():
    assert normalise_record(CHANNEL_SAMPLES["email"]).labels == {"intent": "api_key_issue"}
    assert normalise_record(CHANNEL_SAMPLES["chat"]).labels is None


def test_ticket_is_immutable():
    t = normalise_record(CHANNEL_SAMPLES["forum"])
    with pytest.raises(Exception):
        t.body = "changed"  # type: ignore[misc]


# --- the real pack files load cleanly ------------------------------------------------------

@pytest.mark.parametrize("name,expected", [("development_tickets.json", 500), ("validation_tickets.json", 80)])
def test_pack_files_load_without_errors_or_warnings(name, expected):
    result = load_tickets(DATA / name)
    assert result.errors == []
    assert len(result.tickets) == expected
    assert {t.channel for t in result.tickets} == {
        Channel.EMAIL, Channel.CHAT, Channel.DOCS_COMMENT, Channel.FORUM}
    assert all(t.ingest_warnings == () for t in result.tickets)


# --- tolerance: missing, empty, aliased, malformed -----------------------------------------

def test_minimal_record_gets_defaults_and_warnings():
    t = normalise_record({"body": "help, nothing works"})
    assert t.ticket_id.startswith("ANON-")
    assert t.channel is Channel.UNKNOWN
    assert t.subject == ""
    assert t.customer_tier == t.customer_region == t.language_fluency == UNKNOWN
    assert t.received_at is None
    for w in ("missing_ticket_id", "unknown_channel:missing", "missing_received_at",
              "missing_customer_tier", "missing_customer_region", "missing_language_fluency"):
        assert w in t.ingest_warnings


def test_synthetic_id_is_deterministic():
    rec = {"body": "same content", "channel": "chat"}
    assert normalise_record(rec).ticket_id == normalise_record(dict(rec)).ticket_id


@pytest.mark.parametrize("body", ["", "   \n\t ", None])
def test_empty_body_is_flagged_not_fatal(body):
    t = normalise_record({"ticket_id": "X", "channel": "chat", "body": body})
    assert t.body == ""
    assert t.is_empty
    assert "empty_body" in t.ingest_warnings
    assert "empty_text" in t.ingest_warnings


def test_empty_body_with_subject_is_not_empty_text():
    t = normalise_record({"ticket_id": "X", "channel": "email", "subject": "Billing", "body": ""})
    assert "empty_body" in t.ingest_warnings
    assert "empty_text" not in t.ingest_warnings
    assert not t.is_empty


def test_field_aliases_are_accepted():
    t = normalise_record({
        "id": "A-1", "source": "Live Chat", "title": "Hi", "message": "Can't log in",
        "created_at": "2026-02-01T10:00:00+05:30", "tier": "Enterprise",
        "region": "North America", "fluency": "Non-Fluent",
    })
    assert t.ticket_id == "A-1"
    assert t.channel is Channel.CHAT
    assert (t.subject, t.body) == ("Hi", "Can't log in")
    assert t.received_at == datetime(2026, 2, 1, 4, 30, tzinfo=timezone.utc)
    assert (t.customer_tier, t.customer_region, t.language_fluency) == (
        "enterprise", "north_america", "non_fluent")


@pytest.mark.parametrize("raw,expected", [
    ("email", Channel.EMAIL), ("EMAIL", Channel.EMAIL), ("e-mail", Channel.EMAIL),
    ("chat", Channel.CHAT), ("docs_comment", Channel.DOCS_COMMENT),
    ("docs-comment", Channel.DOCS_COMMENT), ("Doc Comment", Channel.DOCS_COMMENT),
    ("forum", Channel.FORUM), ("community", Channel.FORUM),
    ("fax", Channel.UNKNOWN), (None, Channel.UNKNOWN), (42, Channel.UNKNOWN),
])
def test_normalise_channel(raw, expected):
    assert normalise_channel(raw) is expected


def test_unknown_channel_is_kept_and_flagged():
    t = normalise_record({"ticket_id": "X", "channel": "fax", "body": "hello"})
    assert t.channel is Channel.UNKNOWN
    assert "unknown_channel:fax" in t.ingest_warnings


@pytest.mark.parametrize("raw,expected", [
    ("2026-05-23T22:43:00Z", datetime(2026, 5, 23, 22, 43, tzinfo=timezone.utc)),
    ("2026-05-23T22:43:00", datetime(2026, 5, 23, 22, 43, tzinfo=timezone.utc)),
    (1_780_000_000, datetime.fromtimestamp(1_780_000_000, tz=timezone.utc)),
    (1_780_000_000_000, datetime.fromtimestamp(1_780_000_000, tz=timezone.utc)),
    ("yesterday", None), ("", None), (None, None), (True, None),
])
def test_parse_timestamp(raw, expected):
    assert parse_timestamp(raw) == expected


def test_bad_timestamp_flagged():
    t = normalise_record({"ticket_id": "X", "channel": "forum", "body": "b", "received_at": "soon"})
    assert t.received_at is None
    assert "bad_received_at" in t.ingest_warnings


def test_clean_text_normalises_whitespace_and_types():
    assert clean_text("  a \t b \r\n\r\n\r\n\r\n c  ") == "a b\n\nc"
    assert clean_text(None) == ""
    assert clean_text(123) == "123"
    assert clean_text("nul\x00byte") == "nulbyte"


def test_non_string_body_is_coerced():
    t = normalise_record({"ticket_id": "X", "channel": "chat", "body": 404})
    assert t.body == "404"


def test_non_dict_labels_are_dropped():
    t = normalise_record({"ticket_id": "X", "channel": "chat", "body": "b", "labels": "oops"})
    assert t.labels is None


# --- batch behaviour -----------------------------------------------------------------------

def test_bad_records_do_not_sink_the_batch():
    result = ingest_records([CHANNEL_SAMPLES["email"], "not a ticket", None, 7, CHANNEL_SAMPLES["chat"]])
    assert [t.ticket_id for t in result.tickets] == ["T-EMAIL", "T-CHAT"]
    assert [e.index for e in result.errors] == [1, 2, 3]


def test_duplicate_ids_are_made_unique_and_flagged():
    rec = {"ticket_id": "DUP", "channel": "chat", "body": "x"}
    result = ingest_records([rec, rec, rec])
    assert [t.ticket_id for t in result.tickets] == ["DUP", "DUP#2", "DUP#3"]
    assert "duplicate_ticket_id" not in result.tickets[0].ingest_warnings
    assert "duplicate_ticket_id" in result.tickets[2].ingest_warnings


# --- file formats and whole-input failures -------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_load_wrapped_tickets_object(tmp_path):
    p = _write(tmp_path, "in.json", json.dumps({"tickets": list(CHANNEL_SAMPLES.values())}))
    assert len(load_tickets(p).tickets) == 4


def test_load_single_ticket_object(tmp_path):
    p = _write(tmp_path, "in.json", json.dumps(CHANNEL_SAMPLES["forum"]))
    assert [t.ticket_id for t in load_tickets(p).tickets] == ["T-FORUM"]


def test_load_jsonl_with_a_bad_line(tmp_path):
    lines = [json.dumps(CHANNEL_SAMPLES["email"]), "{broken", "", json.dumps(CHANNEL_SAMPLES["chat"])]
    p = _write(tmp_path, "in.jsonl", "\n".join(lines))
    result = load_tickets(p)
    assert len(result.tickets) == 2
    assert len(result.errors) == 1 and result.errors[0].index == 1


def test_load_utf8_bom(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps([CHANNEL_SAMPLES["chat"]]).encode())
    assert len(load_tickets(p).tickets) == 1


def test_empty_list_is_valid(tmp_path):
    result = load_tickets(_write(tmp_path, "in.json", "[]"))
    assert result.tickets == [] and result.errors == []


@pytest.mark.parametrize("content", ["{not json", '"just a string"', '{"foo": 1}', "42"])
def test_unreadable_input_raises_ingest_error(tmp_path, content):
    with pytest.raises(IngestError):
        load_tickets(_write(tmp_path, "in.json", content))


def test_missing_file_raises_ingest_error(tmp_path):
    with pytest.raises(IngestError, match="not found"):
        load_tickets(tmp_path / "nope.json")
