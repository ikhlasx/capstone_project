"""HTTP API for the triage pipeline.

    uvicorn src.api:app --port 8000

Endpoints:
    GET  /health    is the service up, is a model provider configured, how many passages are indexed
    POST /tickets   process one ticket from any channel; returns the reply or the escalation packet
    GET  /metrics   Prometheus metrics

A ticket problem never produces a 500: a ticket the pipeline cannot handle comes back as an
escalation. Only a request body that is not a JSON object is rejected (422).
"""
from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException, Response
from pydantic import BaseModel

from . import metrics_server
from .config import get_settings
from .ingest import normalise_record
from .pipeline import EscalationPacket, Pipeline, build_pipeline, emergency_escalation


class TicketResponse(BaseModel):
    ticket_id: str
    action: str                       # "auto_respond" or "escalate"
    rule: str
    reason: str
    intent: str | None
    intent_confidence: float | None
    urgency: str | None
    reply: str | None
    citations: list[str]
    escalation: EscalationPacket | None
    ingest_warnings: list[str]
    triage_ms: float
    total_ms: float


def default_pipeline() -> Pipeline:
    settings = get_settings()
    return build_pipeline(settings, database_url=settings.database_url, run_id=f"api-{uuid.uuid4().hex[:8]}")


def create_app(pipeline_factory: Callable[[], Pipeline] = default_pipeline) -> FastAPI:
    state: dict[str, Pipeline] = {}
    lock = threading.Lock()   # the models are not thread-safe, so tickets are processed one at a time

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state["pipeline"] = pipeline_factory()      # loads models once, at start-up
        yield
        state["pipeline"].log.close()

    app = FastAPI(title="CloudServe Support Triage", version="1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, Any]:
        p = state["pipeline"]
        try:
            indexed = p.retriever.count()
        except Exception:
            indexed = 0
        return {"status": "ok" if indexed else "degraded",
                "indexed_passages": indexed,
                "classifier_version": getattr(p.classifier, "version", "unknown"),
                "provider": p.generator.provider.name if p.generator else None,
                "can_draft_answers": p.generator is not None,
                "confidence_threshold": p.routing.confidence_threshold,
                "relevance_threshold": p.routing.relevance_threshold}

    @app.post("/tickets", response_model=TicketResponse)
    def process_ticket(ticket: Any = Body(...)) -> TicketResponse:
        if not isinstance(ticket, dict):
            raise HTTPException(status_code=422, detail="The request body must be a JSON object describing one ticket.")
        t = normalise_record(ticket)
        with lock:
            try:
                result = state["pipeline"].process(t)
            except Exception as exc:               # e.g. the decision log cannot be written
                result = emergency_escalation(t, exc)
        metrics_server.record(result)
        c = result.classification
        return TicketResponse(
            ticket_id=result.ticket_id, action=result.action, rule=result.rule, reason=result.reason,
            intent=c.intent if c else None, intent_confidence=c.intent_confidence if c else None,
            urgency=c.urgency if c else None, reply=result.reply, citations=result.citations,
            escalation=result.packet, ingest_warnings=list(t.ingest_warnings),
            triage_ms=result.triage_ms, total_ms=result.total_ms)

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(content=metrics_server.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    return app


app = create_app()
