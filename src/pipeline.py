"""The full ticket pipeline: classify -> retrieve -> route -> generate -> validate -> act -> log.

`Pipeline.process` never raises. Whatever goes wrong at any stage (classifier error, missing
index, provider outage, malformed model output), the ticket is escalated to a person with a
context packet and the failure is recorded in the decision log (A11).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, Field

from .classify import Classification, TicketClassifier
from .config import OPENROUTER_BASE_URL, Settings
from .generate import Draft, GenerationFailed, Generator, LLMCache, OpenRouterProvider, Provider
from .guardrails import GuardrailReport, finalise_reply, redact_pii, validate
from .logging_store import DecisionLog, DecisionRecord
from .models import Ticket
from .retrieve import Passage, Retriever, SentenceTransformerEmbedder
from .route import RouteDecision, RoutingConfig, route

URGENCY_ORDER = {"high": 0, "medium": 1, "low": 2}
RETRIEVAL_MODEL = {"name": "chroma-cosine", "version": "1"}
RULES_MODEL = {"name": "routing-rules", "version": "1"}
GUARDRAIL_MODEL = {"name": "guardrail-rules", "version": "1"}


class EscalationPacket(BaseModel):
    """What a person receives with an escalated ticket (FR-08)."""

    ticket_id: str
    channel: str
    received_at: datetime | None
    customer_tier: str
    summary: str
    likely_intent: str
    intent_confidence: float
    urgency: str
    reason: str
    rule: str
    unsure_about: str
    retrieved: list[dict[str, Any]] = Field(default_factory=list)   # chunk_id, doc_id, title, section, score
    blocked_draft: str | None = None          # a draft the guardrails stopped, for the agent to judge
    guardrail_failures: dict[str, str] = Field(default_factory=dict)
    ingest_warnings: list[str] = Field(default_factory=list)


class TicketResult(BaseModel):
    ticket_id: str
    action: Literal["auto_respond", "escalate"]
    rule: str
    reason: str
    blocked_by_guardrails: bool = False
    generation_failed: bool = False
    error: str | None = None
    classification: Classification | None = None
    passages: list[Passage] = Field(default_factory=list)
    reply: str | None = None
    citations: list[str] = Field(default_factory=list)
    guardrails: dict[str, str] = Field(default_factory=dict)
    pii_types: list[str] = Field(default_factory=list)
    packet: EscalationPacket | None = None
    cached: bool = False
    triage_ms: float = 0.0
    total_ms: float = 0.0


def summarise(ticket: Ticket, c: Classification | None) -> str:
    text = " ".join(redact_pii(ticket.text).split())
    head = f"{c.intent} ({c.urgency} urgency)" if c else "unclassified"
    return f"{head}, via {ticket.channel.value}: {text[:240]}{'…' if len(text) > 240 else ''}" if text \
        else f"{head}, via {ticket.channel.value}: (empty ticket)"


def input_summary(ticket: Ticket) -> str:
    return " ".join(redact_pii(ticket.text).split())[:160] or "(empty ticket)"


def sort_escalations(packets: Sequence[EscalationPacket]) -> list[EscalationPacket]:
    """Urgency first, then oldest first (FR-09). Tickets with no timestamp go last in their band."""
    far_future = datetime.max.replace(tzinfo=timezone.utc)
    return sorted(packets, key=lambda p: (URGENCY_ORDER.get(p.urgency, 1), p.received_at or far_future, p.ticket_id))


def emergency_escalation(ticket: Ticket, exc: Exception) -> TicketResult:
    """Last line of defence: if processing itself blows up, hand the ticket to a person."""
    reason = f"Unexpected error while processing ({type(exc).__name__}); a person must handle this ticket."
    return TicketResult(
        ticket_id=ticket.ticket_id, action="escalate", rule="internal_error", reason=reason, error=type(exc).__name__,
        packet=EscalationPacket(ticket_id=ticket.ticket_id, channel=ticket.channel.value, received_at=ticket.received_at,
                                customer_tier=ticket.customer_tier, summary=summarise(ticket, None),
                                likely_intent="unknown", intent_confidence=0.0, urgency="medium",
                                reason=reason, rule="internal_error", unsure_about="",
                                ingest_warnings=list(ticket.ingest_warnings)))


class Pipeline:
    def __init__(self, classifier: TicketClassifier, retriever: Retriever, generator: Generator | None,
                 log: DecisionLog, routing: RoutingConfig = RoutingConfig(), top_k: int = 5):
        self.classifier = classifier
        self.retriever = retriever
        self.generator = generator          # None when no API key is configured
        self.log = log
        self.routing = routing
        self.top_k = top_k

    # --- helpers ---------------------------------------------------------------------------

    def _packet(self, t: Ticket, c: Classification | None, passages: Sequence[Passage], rule: str, reason: str,
                unsure: str = "", draft: Draft | None = None, report: GuardrailReport | None = None) -> EscalationPacket:
        return EscalationPacket(
            ticket_id=t.ticket_id, channel=t.channel.value, received_at=t.received_at,
            customer_tier=t.customer_tier, summary=summarise(t, c),
            likely_intent=c.intent if c else "unknown", intent_confidence=c.intent_confidence if c else 0.0,
            urgency=c.urgency if c else "medium", reason=reason, rule=rule,
            unsure_about=unsure or ("" if c is None or c.intent_confidence >= self.routing.confidence_threshold
                                    else f"Intent is uncertain; alternatives: "
                                         f"{', '.join(f'{a.value} ({a.confidence:.2f})' for a in c.alternatives)}"),
            retrieved=[{"chunk_id": p.chunk_id, "doc_id": p.doc_id, "title": p.title,
                        "section": p.section, "score": p.score} for p in passages],
            blocked_draft=draft.answer if (draft and report and not report.passed) else None,
            guardrail_failures={k: v for k, v in (report.results if report else {}).items() if v != "pass"},
            ingest_warnings=list(t.ingest_warnings),
        )

    def _sources(self, passages: Sequence[Passage]) -> list[dict[str, Any]]:
        return [{"doc_id": p.doc_id, "chunk_id": p.chunk_id, "score": p.score} for p in passages]

    # --- the pipeline ----------------------------------------------------------------------

    def process(self, ticket: Ticket) -> TicketResult:
        started = time.perf_counter()
        summary = input_summary(ticket)
        c: Classification | None = None
        passages: list[Passage] = []
        errors: list[str] = []

        # 1. classify
        try:
            c = self.classifier.predict(ticket)
            self.log.log(DecisionRecord(
                ticket_id=ticket.ticket_id, stage="classification", input_summary=summary,
                model={"name": c.model_name, "version": c.model_version},
                prediction={"value": c.intent, "confidence": c.intent_confidence,
                            "urgency": c.urgency, "urgency_confidence": c.urgency_confidence},
                alternatives=[a.model_dump() for a in c.alternatives],
                action_taken="continue", reason="classified", requirement_ids=["FR-02"]))
        except Exception as exc:
            errors.append(f"classifier_error: {type(exc).__name__}")
            self.log.log(DecisionRecord(
                ticket_id=ticket.ticket_id, stage="classification", input_summary=summary,
                model={"name": TicketClassifier.MODEL_NAME, "version": "unavailable"},
                prediction={"value": None, "confidence": 0.0}, action_taken="escalate",
                reason=errors[-1], requirement_ids=["FR-02"]))

        # 2. retrieve (unfiltered top-k; routing applies the relevance threshold)
        if c is not None and not ticket.is_empty:
            try:
                passages = self.retriever.search(ticket.text, top_k=self.top_k)
            except Exception as exc:
                errors.append(f"retrieval_error: {type(exc).__name__}")

        # 3. route
        if c is None:
            decision = RouteDecision(action="escalate", rule="classifier_unavailable",
                                     reason="The classifier failed, so a person must triage this ticket.",
                                     threshold_applied={}, requirement_ids=("FR-05",))
        else:
            decision = route(ticket, c, passages, self.routing)
            if decision.action == "escalate" and decision.rule == "no_relevant_passage" and errors:
                decision = decision.model_copy(update={"rule": "retrieval_unavailable",
                                                       "reason": "Document search failed, so no answer can be grounded."})
        relevant = [p for p in passages if p.score >= self.routing.relevance_threshold]
        self.log.log(DecisionRecord(
            ticket_id=ticket.ticket_id, stage="routing", input_summary=summary, model=RULES_MODEL,
            prediction={"value": decision.action, "confidence": c.intent_confidence if c else 0.0, "rule": decision.rule},
            sources_used=self._sources(relevant), threshold_applied=decision.threshold_applied,
            action_taken="continue" if decision.action == "generate" else "escalate",
            reason=decision.reason, requirement_ids=list(decision.requirement_ids)))
        triage_ms = (time.perf_counter() - started) * 1000

        def escalate(rule: str, reason: str, **kw) -> TicketResult:
            return TicketResult(
                ticket_id=ticket.ticket_id, action="escalate", rule=rule, reason=reason,
                classification=c, passages=relevant, error="; ".join(errors) or None,
                packet=self._packet(ticket, c, relevant, rule, reason,
                                    unsure=kw.pop("unsure", ""), draft=kw.pop("draft", None), report=kw.pop("report", None)),
                triage_ms=round(triage_ms, 1), total_ms=round((time.perf_counter() - started) * 1000, 1), **kw)

        if decision.action == "escalate":
            return escalate(decision.rule, decision.reason)

        # 4. generate
        try:
            if self.generator is None:
                raise GenerationFailed("no_api_key", "no model provider is configured")
            draft = self.generator.generate(ticket, relevant)
        except Exception as exc:
            code = exc.reason if isinstance(exc, GenerationFailed) else f"unexpected_{type(exc).__name__}"
            reason = f"Answer drafting failed ({code}); a person should reply."
            self.log.log(DecisionRecord(
                ticket_id=ticket.ticket_id, stage="generation", input_summary=summary,
                model={"name": self.generator.model if self.generator else "none", "version": "n/a"},
                prediction={"value": None, "confidence": 0.0}, sources_used=self._sources(relevant),
                action_taken="escalate", reason=reason,
                prompt_version=self.generator.prompt.label if self.generator else None,
                requirement_ids=["FR-06", "NFR-02"]))
            return escalate(f"generation_failed:{code}", reason, generation_failed=True)

        self.log.log(DecisionRecord(
            ticket_id=ticket.ticket_id, stage="generation", input_summary=summary,
            model={"name": draft.model, "version": "cached" if draft.cached else "live"},
            prediction={"value": "draft" if draft.can_answer else "declined", "confidence": c.intent_confidence,
                        "citations": list(draft.citations), "attempts": draft.attempts},
            sources_used=self._sources(relevant), action_taken="continue",
            reason=draft.unsure_about or "drafted from retrieved passages",
            prompt_version=draft.prompt_version, requirement_ids=["FR-06"]))

        # 5. validate
        report = validate(ticket, draft, relevant)
        self.log.log(DecisionRecord(
            ticket_id=ticket.ticket_id, stage="validation", input_summary=summary, model=GUARDRAIL_MODEL,
            prediction={"value": "pass" if report.passed else "block", "confidence": 1.0},
            sources_used=self._sources(relevant), threshold_applied=decision.threshold_applied,
            action_taken="auto_respond" if report.passed else "block",
            reason="all checks passed" if report.passed else f"blocked by: {', '.join(report.blocked_by)}",
            guardrail_results=report.as_log(), prompt_version=draft.prompt_version,
            requirement_ids=["FR-07", "FR-10"]))

        if not report.passed:
            reason = f"A drafted answer was blocked by: {', '.join(report.blocked_by)}."
            return escalate("guardrail_block", reason, blocked_by_guardrails=True, guardrails=report.results,
                            pii_types=list(report.pii_types), unsure=draft.unsure_about, draft=draft,
                            report=report, cached=draft.cached)

        # 6. act
        return TicketResult(
            ticket_id=ticket.ticket_id, action="auto_respond", rule=decision.rule, reason=decision.reason,
            classification=c, passages=relevant, reply=finalise_reply(draft, relevant),
            citations=sorted(set(draft.citations)), guardrails=report.results, cached=draft.cached,
            triage_ms=round(triage_ms, 1), total_ms=round((time.perf_counter() - started) * 1000, 1))


# --- assembly ------------------------------------------------------------------------------

def build_pipeline(settings: Settings, database_url: str, run_id: str | None = None,
                   provider: Provider | None | Literal["auto"] = "auto", embedder=None) -> Pipeline:
    """Wire the pipeline from settings. Builds the index and trains the classifier if they are
    missing, so a clean checkout works with one command."""
    from .chunking import chunk_corpus, load_corpus
    from .ingest import load_tickets
    from .retrieve import RetrievalUnavailable

    embedder = embedder or SentenceTransformerEmbedder(settings.embedding_model)

    retriever = Retriever(embedder, settings.chroma_path)
    try:
        retriever.count()
    except RetrievalUnavailable:
        retriever.build(chunk_corpus(load_corpus(settings.docs_path)))

    try:
        classifier = TicketClassifier.load(settings.classifier_path, embedder)
    except (FileNotFoundError, RuntimeError):
        classifier = TicketClassifier(embedder).fit(load_tickets(settings.training_data).tickets)
        classifier.save(settings.classifier_path)

    if provider == "auto":
        provider = OpenRouterProvider(settings.openrouter_api_key, OPENROUTER_BASE_URL) if settings.has_api_key else None
    generator = Generator(provider, settings.model_name, cache=LLMCache(settings.cache_path)) if provider else None

    return Pipeline(classifier, retriever, generator, DecisionLog(database_url, run_id=run_id),
                    RoutingConfig(confidence_threshold=settings.confidence_threshold,
                                  relevance_threshold=settings.relevance_threshold),
                    top_k=settings.retrieval_top_k)
