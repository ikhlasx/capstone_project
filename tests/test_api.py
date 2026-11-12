"""Tests for the HTTP API and the Prometheus metrics. No API key or model download needed."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src import metrics_server
from src.api import create_app
from src.generate import Generator, StubProvider
from src.guardrails import DISCLOSURE
from src.logging_store import DecisionLog
from src.pipeline import Pipeline
from src.route import RoutingConfig

ROUTING = RoutingConfig(confidence_threshold=0.30, relevance_threshold=0.20)  # scaled for the fake embedder


def metric(name: str, **labels) -> float:
    """Read one value out of the Prometheus text output (0.0 if the series does not exist yet)."""
    text = metrics_server.render().decode()
    want = "".join(sorted(f'{k}="{v}"' for k, v in labels.items()))
    for line in text.splitlines():
        m = re.match(rf"^{name}(?:\{{(.*)\}})? ([0-9.e+-]+)$", line)
        if m and "".join(sorted((m.group(1) or "").split(","))) == want:
            return float(m.group(2))
    return 0.0


@pytest.fixture
def client(fake_classifier, fake_retriever, tmp_path):
    def factory(provider=StubProvider()):
        gen = Generator(provider, "test-model") if provider else None
        return Pipeline(fake_classifier, fake_retriever, gen, DecisionLog(str(tmp_path / "api.db"), run_id="api-test"), ROUTING)

    with TestClient(create_app(factory)) as c:
        yield c


ANSWERABLE = {"ticket_id": "API-1", "channel": "email", "subject": "How do I revert to the previous revision",
              "body": "How do I revert to an earlier revision? The release we put out this morning is causing errors "
                      "and I would rather roll back than debug it live."}
PROTECTED = {"ticket_id": "API-2", "channel": "chat", "body": "set from the dev set by the fixture below"}


@pytest.fixture(autouse=True)
def real_security_ticket(dev_set):
    """Use a real security-incident ticket, so the stand-in classifier recognises it."""
    t = next(t for t in dev_set if t.labels["intent"] == "security_incident")
    PROTECTED.update(subject=t.subject, body=t.body)


def test_health_reports_index_and_provider(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["indexed_passages"] == 116
    assert body["can_draft_answers"] is True and body["provider"] == "stub"
    assert body["confidence_threshold"] == 0.30


def test_answerable_ticket_returns_a_disclosed_reply(client):
    r = client.post("/tickets", json=ANSWERABLE)
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "auto_respond" and body["escalation"] is None
    assert DISCLOSURE in body["reply"] and body["citations"]
    assert body["intent"] == "rollback_request" and 0 <= body["intent_confidence"] <= 1


def test_protected_ticket_returns_an_escalation_packet(client):
    body = client.post("/tickets", json=PROTECTED).json()
    assert body["action"] == "escalate" and body["rule"] == "protected_intent" and body["reply"] is None
    assert body["escalation"]["summary"] and body["escalation"]["likely_intent"] == "security_incident"


@pytest.mark.parametrize("payload,rule", [
    ({"ticket_id": "API-3", "channel": "chat", "body": ""}, "empty_ticket"),
    ({"body": None}, "empty_ticket"),
    ({}, "empty_ticket"),
])
def test_bad_tickets_are_escalated_not_errors(client, payload, rule):
    r = client.post("/tickets", json=payload)
    assert r.status_code == 200 and r.json()["action"] == "escalate" and r.json()["rule"] == rule


def test_missing_fields_are_reported_as_ingest_warnings(client):
    body = client.post("/tickets", json={"message": "How do I roll back the latest release?", "source": "forum"}).json()
    assert body["ticket_id"].startswith("ANON-")
    assert "missing_ticket_id" in body["ingest_warnings"]


@pytest.mark.parametrize("payload", ["a string", ["a", "list"], 42])
def test_non_object_body_is_rejected_with_422(client, payload):
    assert client.post("/tickets", json=payload).status_code == 422


def test_metrics_endpoint_counts_processed_tickets(client):
    before_auto = metric("triage_tickets_total", action="auto_respond", rule="answerable")
    before_esc = metric("triage_tickets_total", action="escalate", rule="protected_intent")
    before_latency = metric("triage_latency_seconds_count")
    client.post("/tickets", json=ANSWERABLE)
    client.post("/tickets", json=PROTECTED)
    text = client.get("/metrics")
    assert text.status_code == 200 and "triage_tickets_total" in text.text
    assert metric("triage_tickets_total", action="auto_respond", rule="answerable") == before_auto + 1
    assert metric("triage_tickets_total", action="escalate", rule="protected_intent") == before_esc + 1
    assert metric("triage_latency_seconds_count") == before_latency + 2
    assert metric("triage_intent_total", intent="security_incident", urgency=client.post("/tickets", json=PROTECTED).json()["urgency"]) >= 1


def test_metrics_count_guardrail_blocks_and_generation_failures(fake_classifier, fake_retriever, tmp_path):
    class Failing:
        name = "failing"

        def complete(self, messages, model):
            raise TimeoutError("timed out")

    def factory():
        gen = Generator(Failing(), "test-model", sleep=lambda s: None)
        return Pipeline(fake_classifier, fake_retriever, gen, DecisionLog(str(tmp_path / "f.db"), run_id="f"), ROUTING)

    before = metric("triage_generation_failures_total", reason="provider_unavailable")
    with TestClient(create_app(factory)) as c:
        body = c.post("/tickets", json=ANSWERABLE).json()
    assert body["action"] == "escalate" and body["rule"] == "generation_failed:provider_unavailable"
    assert metric("triage_generation_failures_total", reason="provider_unavailable") == before + 1


def test_api_works_without_a_provider(fake_classifier, fake_retriever, tmp_path):
    def factory():
        return Pipeline(fake_classifier, fake_retriever, None, DecisionLog(str(tmp_path / "n.db"), run_id="n"), ROUTING)

    with TestClient(create_app(factory)) as c:
        assert c.get("/health").json()["can_draft_answers"] is False
        assert c.post("/tickets", json=ANSWERABLE).json()["rule"] == "generation_failed:no_api_key"
