"""Tests for the classifier (A3), deterministic routing (A5) and the decision log (A8)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.classify import Alternative, Classification, TicketClassifier
from src.ingest import load_tickets, normalise_record
from src.logging_store import DecisionLog, DecisionRecord, sqlite_path
from src.retrieve import Passage
from src.route import ALWAYS_ESCALATE, RoutingConfig, is_billing_dispute, route
from tests.helpers import FakeEmbedder

DATA = Path(__file__).resolve().parent.parent / "data"


# --- helpers -------------------------------------------------------------------------------

def ticket(body="How do I rotate an API key?", subject="", **kw):
    return normalise_record({"ticket_id": "T-1", "channel": "email", "subject": subject, "body": body,
                             "received_at": "2026-03-02T08:32:00Z", "customer_tier": "standard",
                             "customer_region": "europe", "language_fluency": "fluent", **kw})


def cls(intent="api_key_issue", conf=0.95, urgency="medium", alts=()):
    return Classification(intent=intent, intent_confidence=conf, urgency=urgency, urgency_confidence=0.5,
                          alternatives=tuple(Alternative(value=v, confidence=c) for v, c in alts),
                          model_name="test", model_version="t1")


def passage(doc="DOC-AUTH-004", score=0.6, section="resolution"):
    return Passage(chunk_id=f"{doc}#{section}", doc_id=doc, title="t", section=section, text="x", score=score)


# --- classifier ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def dev_tickets():
    return load_tickets(DATA / "development_tickets.json").tickets


@pytest.fixture(scope="module")
def clf(dev_tickets):
    return TicketClassifier(FakeEmbedder()).fit(dev_tickets)


def test_prediction_has_intent_urgency_confidence_and_alternatives(clf, dev_tickets):
    c = clf.predict(dev_tickets[0])
    assert c.intent == dev_tickets[0].labels["intent"]
    assert 0.0 <= c.intent_confidence <= 1.0
    assert c.urgency in {"low", "medium", "high"} and 0.0 <= c.urgency_confidence <= 1.0
    assert len(c.alternatives) == 3
    assert c.intent not in [a.value for a in c.alternatives]
    confs = [a.confidence for a in c.alternatives]
    assert confs == sorted(confs, reverse=True) and confs[0] <= c.intent_confidence
    assert c.model_name and c.model_version.startswith("fake-bow-256-n500-")


def test_knows_all_22_intents_and_3_urgencies(clf):
    assert len(clf.intent_head.classes_) == 22
    assert set(clf.urgency_head.classes_) == {"low", "medium", "high"}
    assert ALWAYS_ESCALATE <= set(clf.intent_head.classes_)


def test_training_accuracy_on_intent_is_high(clf, dev_tickets):
    preds = clf.predict_many(dev_tickets)
    acc = sum(p.intent == t.labels["intent"] for p, t in zip(preds, dev_tickets)) / len(dev_tickets)
    assert acc > 0.95


def test_classifier_is_deterministic(clf, dev_tickets):
    assert clf.predict(dev_tickets[7]) == clf.predict(dev_tickets[7])


def test_empty_ticket_gets_zero_confidence_unclear(clf):
    c = clf.predict(ticket(body=""))
    assert (c.intent, c.intent_confidence, c.alternatives) == ("unclear_request", 0.0, ())


def test_predict_many_keeps_order_with_empty_tickets(clf, dev_tickets):
    batch = [dev_tickets[0], ticket(body="   "), dev_tickets[1]]
    out = clf.predict_many(batch)
    assert [c.intent_confidence == 0.0 for c in out] == [False, True, False]
    assert out[2].intent == dev_tickets[1].labels["intent"]


def test_untrained_classifier_refuses_to_predict():
    with pytest.raises(RuntimeError, match="not trained"):
        TicketClassifier(FakeEmbedder()).predict(ticket())


def test_too_few_training_tickets_is_an_error(dev_tickets):
    with pytest.raises(ValueError, match="at least 50"):
        TicketClassifier(FakeEmbedder()).fit(dev_tickets[:10])


def test_save_and_load_round_trip(clf, dev_tickets, tmp_path):
    path = tmp_path / "models" / "clf.joblib"
    clf.save(path)
    loaded = TicketClassifier.load(path, FakeEmbedder())
    assert loaded.predict(dev_tickets[3]) == clf.predict(dev_tickets[3])


def test_load_rejects_a_different_embedder(clf, tmp_path):
    path = tmp_path / "clf.joblib"
    clf.save(path)

    class Other(FakeEmbedder):
        name = "other-model"

    with pytest.raises(RuntimeError, match="retrain"):
        TicketClassifier.load(path, Other())


# --- routing -------------------------------------------------------------------------------

@pytest.mark.parametrize("intent", sorted(ALWAYS_ESCALATE))
def test_protected_intents_always_escalate(intent):
    d = route(ticket(), cls(intent=intent, conf=0.999), [passage(score=0.99)])
    assert (d.action, d.rule) == ("escalate", "protected_intent")
    assert "FR-04" in d.requirement_ids


def test_protected_runner_up_escalates_only_above_margin():
    alts_close = (("security_incident", 0.20), ("billing_query", 0.01), ("onboarding", 0.01))
    alts_far = (("security_incident", 0.05), ("billing_query", 0.01), ("onboarding", 0.01))
    assert route(ticket(), cls(conf=0.85, alts=alts_close), [passage()]).rule == "possible_protected_intent"
    assert route(ticket(), cls(conf=0.85, alts=alts_far), [passage()]).action == "generate"


def test_low_confidence_escalates():
    d = route(ticket(), cls(conf=0.79), [passage()], RoutingConfig(confidence_threshold=0.80))
    assert (d.action, d.rule) == ("escalate", "low_confidence")
    assert d.threshold_applied["confidence"] == 0.80


def test_protected_rule_wins_over_low_confidence():
    assert route(ticket(), cls(intent="security_incident", conf=0.10), []).rule == "protected_intent"


def test_no_relevant_passage_escalates():
    assert route(ticket(), cls(), []).rule == "no_relevant_passage"
    assert route(ticket(), cls(), [passage(score=0.39)], RoutingConfig(relevance_threshold=0.40)).rule == "no_relevant_passage"


def test_confident_ticket_with_relevant_passage_is_answered():
    d = route(ticket(), cls(), [passage(score=0.41)], RoutingConfig(relevance_threshold=0.40))
    assert (d.action, d.rule) == ("generate", "answerable")
    assert "FR-06" in d.requirement_ids


def test_empty_ticket_escalates_before_anything_else():
    assert route(ticket(body=""), cls(), [passage()]).rule == "empty_ticket"


@pytest.mark.parametrize("text,is_dispute", [
    ("I want to dispute this charge on our invoice", True),
    ("We were overcharged last month, please refund the difference", True),
    ("You charged us twice for the same period", True),
    ("We have raised a chargeback with our bank", True),
    ("There are charges on our invoice for a service I do not believe we use. Could you explain?", False),
    ("Our invoice this month is considerably higher than usual and I cannot see why", False),
    ("How is proration calculated when changing plans?", False),
])
def test_billing_dispute_detection(text, is_dispute):
    assert is_billing_dispute(ticket(body=text)) is is_dispute


def test_billing_dispute_escalates_but_billing_question_is_answered():
    c = cls(intent="billing_query")
    p = [passage(doc="DOC-BILL-001")]
    assert route(ticket(body="Please refund the overcharge"), c, p).rule == "billing_dispute"
    assert route(ticket(body="How do I read the usage breakdown?"), c, p).action == "generate"
    assert route(ticket(body="Please refund the overcharge"), c, p, RoutingConfig(dispute_rule=False)).action == "generate"


def test_dispute_wording_only_matters_for_billing_tickets():
    assert route(ticket(body="Can I get a refund of my API quota?"), cls(intent="quota_or_overage"),
                 [passage(doc="DOC-BILL-003")]).action == "generate"


def test_residency_needs_the_residency_article():
    c = cls(intent="data_residency")
    assert route(ticket(), c, [passage(doc="DOC-DATA-001")]).rule == "residency_without_source"
    assert route(ticket(), c, [passage(doc="DOC-DATA-003", score=0.30)]).rule == "residency_without_source"
    assert route(ticket(), c, [passage(doc="DOC-DATA-003")]).action == "generate"


def test_incident_rule_is_off_by_default_and_optional():
    c = cls(intent="database_issue", urgency="high")
    p = [passage(doc="DOC-PERF-003")]
    assert route(ticket(), c, p).action == "generate"
    assert route(ticket(), c, p, RoutingConfig(incident_rule=True)).rule == "high_urgency_incident"
    assert route(ticket(), cls(intent="database_issue", urgency="medium"), p, RoutingConfig(incident_rule=True)).action == "generate"


def test_routing_is_deterministic():
    args = (ticket(), cls(conf=0.9), [passage()])
    assert route(*args) == route(*args)


# --- decision log --------------------------------------------------------------------------

def record(ticket_id="T-1", stage="classification", **kw):
    base = dict(ticket_id=ticket_id, stage=stage, input_summary="How do I rotate a key?",
                model={"name": "m", "version": "1"}, prediction={"value": "api_key_issue", "confidence": 0.95},
                alternatives=[{"value": "security_incident", "confidence": 0.02}],
                sources_used=[{"doc_id": "DOC-AUTH-004", "score": 0.61}],
                threshold_applied={"confidence": 0.8}, action_taken="continue", reason="classified",
                guardrail_results={"pii": "pass"}, prompt_version=None, requirement_ids=["FR-02"])
    return DecisionRecord(**{**base, **kw})


def test_log_round_trips_every_governance_field(tmp_path):
    log = DecisionLog(f"sqlite:///{tmp_path / 'sub' / 'decisions.db'}", run_id="run-a")
    rid = log.log(record())
    [row] = log.for_ticket("T-1")
    assert row["decision_id"] == rid and row["run_id"] == "run-a"
    for field in ["decision_id", "timestamp", "ticket_id", "stage", "input_summary", "model", "prediction",
                  "alternatives", "sources_used", "threshold_applied", "action_taken", "reason",
                  "guardrail_results", "prompt_version", "requirement_ids"]:
        assert field in row
    assert row["prediction"] == {"value": "api_key_issue", "confidence": 0.95}
    assert row["sources_used"] == [{"doc_id": "DOC-AUTH-004", "score": 0.61}]
    assert row["requirement_ids"] == ["FR-02"]
    assert (tmp_path / "sub" / "decisions.db").exists()


def test_counts_reconcile_per_stage_and_per_run(tmp_path):
    url = str(tmp_path / "d.db")
    a = DecisionLog(url, run_id="run-a")
    for tid in ("T-1", "T-2", "T-3"):
        a.log(record(tid, "classification"))
        a.log(record(tid, "routing", action_taken="escalate"))
    a.log(record("T-1", "generation"))
    b = DecisionLog(url, run_id="run-b")
    b.log(record("T-9", "classification"))
    assert a.count_by_stage() == {"classification": 3, "routing": 3, "generation": 1}
    assert a.tickets_by_stage() == {"classification": 3, "routing": 3, "generation": 1}
    assert b.count_by_stage() == {"classification": 1}
    assert a.for_ticket("T-9") == []


def test_invalid_stage_or_action_is_rejected():
    with pytest.raises(Exception):
        record(stage="guessing")
    with pytest.raises(Exception):
        record(action_taken="maybe")


@pytest.mark.parametrize("url,expected", [
    ("sqlite:///./storage/decisions.db", "./storage/decisions.db"),
    ("storage/x.db", "storage/x.db"), (":memory:", ":memory:"),
])
def test_sqlite_path(url, expected):
    assert sqlite_path(url) == expected


def test_non_sqlite_url_is_rejected():
    with pytest.raises(ValueError):
        sqlite_path("postgresql://user@host/db")
