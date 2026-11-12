"""End-to-end tests for the pipeline, the metrics and the harness (A8, A9, A10, A11).

Everything runs with the fake embedder and a stub or scripted provider: no API key, no model
download, so these tests also run in CI.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evaluation.harness import infer_label, main, run
from evaluation.metrics import compute_metrics, to_markdown
from src.chunking import chunk_corpus, load_corpus
from src.classify import TicketClassifier
from src.generate import Generator, StubProvider
from src.guardrails import DISCLOSURE
from src.ingest import load_tickets, normalise_record
from src.logging_store import DecisionLog
from src.pipeline import EscalationPacket, Pipeline, sort_escalations
from src.retrieve import Retriever
from src.route import RoutingConfig
from tests.helpers import FakeEmbedder

DATA = Path(__file__).resolve().parent.parent / "data"
# The fake embedder gives lower confidences and scores than the real model, so the thresholds
# are lowered for these tests. The routing logic under test is the same.
ROUTING = RoutingConfig(confidence_threshold=0.30, relevance_threshold=0.20)


class Scripted:
    name = "scripted"

    def __init__(self, item):
        self.item = item
        self.calls = 0

    def complete(self, messages, model):
        self.calls += 1
        if isinstance(self.item, Exception):
            raise self.item
        return self.item


@pytest.fixture(scope="module")
def dev():
    return load_tickets(DATA / "development_tickets.json").tickets


@pytest.fixture(scope="module")
def classifier(dev):
    return TicketClassifier(FakeEmbedder()).fit(dev)


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    r = Retriever(FakeEmbedder(), tmp_path_factory.mktemp("idx") / "chroma")
    r.build(chunk_corpus(load_corpus(DATA / "documentation.json")))
    return r


def make(classifier, retriever, tmp_path, provider=StubProvider(), routing=ROUTING):
    generator = Generator(provider, "test-model", sleep=lambda s: None) if provider else None
    return Pipeline(classifier, retriever, generator, DecisionLog(str(tmp_path / "d.db"), run_id="t"), routing)


def first(dev, **want):
    return next(t for t in dev if all(t.labels[k] == v for k, v in want.items()))


# --- the pipeline, path by path ------------------------------------------------------------

def test_answerable_ticket_gets_a_disclosed_cited_reply_and_four_log_rows(classifier, retriever, tmp_path, dev):
    p = make(classifier, retriever, tmp_path)
    t = first(dev, intent="rollback_request", expected_route="auto_respond")
    r = p.process(t)
    assert r.action == "auto_respond" and r.rule == "answerable"
    assert DISCLOSURE in r.reply and r.citations and r.packet is None
    assert set(r.citations) <= {x.chunk_id for x in r.passages}
    stages = [row["stage"] for row in p.log.for_ticket(t.ticket_id)]
    assert stages == ["classification", "routing", "generation", "validation"]
    last = p.log.for_ticket(t.ticket_id)[-1]
    assert last["action_taken"] == "auto_respond" and last["prompt_version"] == "PR-01@1.0"
    assert last["requirement_ids"] == ["FR-07", "FR-10"]


def test_protected_ticket_is_escalated_with_a_complete_packet_and_no_model_call(classifier, retriever, tmp_path, dev):
    provider = Scripted("{}")
    p = make(classifier, retriever, tmp_path, provider)
    t = first(dev, intent="security_incident")
    r = p.process(t)
    assert r.action == "escalate" and r.rule == "protected_intent" and r.reply is None
    assert provider.calls == 0
    k = r.packet
    assert k.summary and k.reason and k.likely_intent == "security_incident" and k.urgency in {"low", "medium", "high"}
    assert [row["stage"] for row in p.log.for_ticket(t.ticket_id)] == ["classification", "routing"]


def test_guardrail_block_turns_a_draft_into_an_escalation(classifier, retriever, tmp_path, dev):
    t = first(dev, intent="rollback_request", expected_route="auto_respond")
    probe = make(classifier, retriever, tmp_path / "a").process(t)
    bad = json.dumps({"can_answer": True, "citations": [probe.citations[0]], "unsure_about": "",
                      "answer": f"We have fixed the issue on our side and a refund has been issued [{probe.citations[0]}]."})
    p = make(classifier, retriever, tmp_path / "b", Scripted(bad))
    r = p.process(t)
    assert r.action == "escalate" and r.rule == "guardrail_block" and r.blocked_by_guardrails
    assert r.reply is None and "forbidden_claims" in r.packet.guardrail_failures
    assert r.packet.blocked_draft.startswith("We have fixed")
    assert p.log.for_ticket(t.ticket_id)[-1]["action_taken"] == "block"


@pytest.mark.parametrize("failure,code", [
    (TimeoutError("timed out"), "provider_unavailable"),
    ("this is not json", "invalid_json"),
])
def test_provider_failure_escalates_instead_of_crashing(classifier, retriever, tmp_path, dev, failure, code):
    p = make(classifier, retriever, tmp_path, Scripted(failure))
    t = first(dev, intent="rollback_request", expected_route="auto_respond")
    r = p.process(t)
    assert r.action == "escalate" and r.generation_failed and r.rule == f"generation_failed:{code}"
    assert r.packet.retrieved, "the packet still carries the retrieved sources"
    assert p.log.for_ticket(t.ticket_id)[-1]["stage"] == "generation"


def test_no_api_key_means_everything_answerable_is_escalated(classifier, retriever, tmp_path, dev):
    p = make(classifier, retriever, tmp_path, provider=None)
    r = p.process(first(dev, intent="rollback_request", expected_route="auto_respond"))
    assert r.action == "escalate" and r.rule == "generation_failed:no_api_key"


def test_empty_ticket_is_escalated(classifier, retriever, tmp_path):
    p = make(classifier, retriever, tmp_path)
    r = p.process(normalise_record({"ticket_id": "E-1", "channel": "chat", "body": "   "}))
    assert r.action == "escalate" and r.rule == "empty_ticket" and "(empty ticket)" in r.packet.summary


def test_missing_index_escalates_instead_of_crashing(classifier, tmp_path, dev):
    empty = Retriever(FakeEmbedder(), tmp_path / "no-index")
    p = make(classifier, empty, tmp_path)
    r = p.process(first(dev, intent="rollback_request", expected_route="auto_respond"))
    assert r.action == "escalate" and r.rule == "retrieval_unavailable" and "retrieval_error" in r.error


def test_classifier_failure_escalates_and_is_logged(retriever, tmp_path, dev):
    class Broken:
        def predict(self, ticket):
            raise RuntimeError("boom")

    p = make(Broken(), retriever, tmp_path)
    r = p.process(dev[0])
    assert r.action == "escalate" and r.rule == "classifier_unavailable"
    assert [row["stage"] for row in p.log.for_ticket(dev[0].ticket_id)] == ["classification", "routing"]


def test_private_data_in_the_ticket_is_masked_in_log_and_packet(classifier, retriever, tmp_path):
    p = make(classifier, retriever, tmp_path)
    t = normalise_record({"ticket_id": "P-1", "channel": "email", "subject": "Suspected account compromise",
                          "body": "Someone signed in as me. Contact jane.doe@example.com or +44 20 7946 0958 urgently."})
    r = p.process(t)
    logged = " ".join(row["input_summary"] for row in p.log.for_ticket("P-1"))
    assert "jane.doe@example.com" not in logged and "jane.doe@example.com" not in r.packet.summary
    assert "[email]" in logged


# --- escalation queue ----------------------------------------------------------------------

def test_queue_is_ordered_by_urgency_then_age():
    def pk(tid, urgency, day):
        return EscalationPacket(ticket_id=tid, channel="email", customer_tier="standard", summary="s",
                                received_at=datetime(2026, 3, day, tzinfo=timezone.utc) if day else None,
                                likely_intent="x", intent_confidence=0.9, urgency=urgency, reason="r", rule="r", unsure_about="")
    queue = sort_escalations([pk("low-old", "low", 1), pk("high-new", "high", 9), pk("med", "medium", 2),
                              pk("high-old", "high", 3), pk("high-undated", "high", None)])
    assert [p.ticket_id for p in queue] == ["high-old", "high-new", "high-undated", "med", "low-old"]


# --- harness and metrics -------------------------------------------------------------------

@pytest.fixture(scope="module")
def report(classifier, retriever, tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    sample = tmp_path_factory.mktemp("in") / "sample.json"
    tickets = json.loads((DATA / "validation_tickets.json").read_text(encoding="utf-8"))
    sample.write_text(json.dumps(tickets + ["not a ticket"]), encoding="utf-8")

    def factory(db_path, run_id):
        return Pipeline(classifier, retriever, Generator(StubProvider(), "test-model"),
                        DecisionLog(db_path, run_id=run_id), ROUTING)

    rep = run(str(sample), str(out), factory, progress=lambda s: None)
    return rep, out


def test_harness_processes_every_ticket_and_writes_all_outputs(report):
    rep, out = report
    assert rep["volume"]["processed"] == 80 and rep["volume"]["ingest_errors"] == 1
    assert rep["volume"]["auto_answered"] + rep["volume"]["escalated"] == 80
    for name in ("metrics.json", "metrics.md", "results.jsonl", "escalation_queue.json", "decisions.db"):
        assert (out / name).exists(), name
    assert len((out / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 80
    assert rep["meta"]["label"] == "validation"


def test_decision_log_reconciles_with_tickets_processed(report):
    g = report[0]["governance"]
    assert g["reconciles"] is True
    assert g["decisions_logged"]["classification"] == 80 and g["decisions_logged"]["routing"] == 80
    assert g["decisions_logged"]["generation"] == g["decisions_expected"]["generation"] > 0


def test_no_protected_ticket_is_auto_answered(report):
    s = report[0]["safety"]
    assert s["protected_tickets"] == 14 and s["auto_responses_on_protected_tickets"] == 0


def test_report_covers_every_required_section(report):
    rep, out = report
    for key in ("volume", "business", "technical", "safety", "governance", "fairness", "answer_quality"):
        assert key in rep
    assert set(rep["fairness"]) == {"tier", "region", "fluency"}
    assert rep["business"]["history_baseline"]["tickets_with_history"] == 80
    assert rep["technical"]["latency_ms"]["total_p95"] is not None
    assert rep["governance"]["auto_replies_with_disclosure"] == 100.0
    assert rep["governance"]["escalations_with_complete_packet"] == 100.0
    md = (out / "metrics.md").read_text(encoding="utf-8")
    for heading in ("## Volume", "## Business outcomes", "## Technical performance", "## Safety",
                    "## Governance", "## Fairness", "## Answer quality"):
        assert heading in md
    assert "validation figures" in md


def test_escalation_queue_file_is_sorted(report):
    queue = json.loads((report[1] / "escalation_queue.json").read_text(encoding="utf-8"))
    order = {"high": 0, "medium": 1, "low": 2}
    keys = [(order[p["urgency"]], p["received_at"]) for p in queue]
    assert keys == sorted(keys) and len(queue) == report[0]["volume"]["escalated"]


def test_metrics_work_without_labels(classifier, retriever, tmp_path):
    p = make(classifier, retriever, tmp_path)
    tickets = [normalise_record({"ticket_id": f"H-{i}", "channel": "chat", "body": b}) for i, b in
               enumerate(["How do I roll back the latest release?", "", "I want to report a security breach on my account"])]
    rows = [(t, p.process(t)) for t in tickets]
    m = compute_metrics(rows, p.log.tickets_by_stage())
    assert m["safety"] is None and "intent_accuracy" not in m["technical"]
    assert m["governance"]["reconciles"] and m["volume"]["processed"] == 3
    assert "no labels" in to_markdown(m, {"label": "hidden/unlabelled", "input": "x", "run_id": "r", "started_at": "now",
                                          "provider": "stub", "model": "m", "confidence_threshold": 0.3,
                                          "relevance_threshold": 0.2}).lower()
    assert infer_label(tickets, "hidden.json") == "hidden/unlabelled"


def test_unreadable_input_exits_cleanly(tmp_path, capsys):
    assert main(["--input", str(tmp_path / "missing.json"), "--output", str(tmp_path / "out"), "--provider", "stub"]) == 2
    assert "Cannot read the input" in capsys.readouterr().out
