"""Prometheus metrics for the pipeline.

`record(result)` updates the counters and histograms for one processed ticket. The API calls it
for every request and exposes the values at `/metrics`. Run this module on its own to serve the
same metrics on a separate port:

    python -m src.metrics_server --port 9100
"""
from __future__ import annotations

import argparse
import time

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest, start_http_server

from .pipeline import TicketResult

REGISTRY = CollectorRegistry()

TICKETS = Counter("triage_tickets_total", "Tickets processed, by final action and deciding rule",
                  ["action", "rule"], registry=REGISTRY)
INTENTS = Counter("triage_intent_total", "Tickets by predicted intent and urgency",
                  ["intent", "urgency"], registry=REGISTRY)
GUARDRAIL_BLOCKS = Counter("triage_guardrail_blocks_total", "Drafts blocked, by the check that failed",
                           ["check"], registry=REGISTRY)
GENERATION_FAILURES = Counter("triage_generation_failures_total", "Answer drafting failures, by reason",
                              ["reason"], registry=REGISTRY)
PII_DETECTIONS = Counter("triage_pii_detections_total", "Drafts in which private data was found",
                         registry=REGISTRY)
STAGE_ERRORS = Counter("triage_stage_errors_total", "Tickets where a pipeline stage raised an error",
                       registry=REGISTRY)
CACHE_HITS = Counter("triage_generation_cache_hits_total", "Drafts served from the response cache",
                     registry=REGISTRY)
TRIAGE_SECONDS = Histogram("triage_latency_seconds", "Time to classify, search and route a ticket",
                           buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 3), registry=REGISTRY)
TOTAL_SECONDS = Histogram("triage_total_latency_seconds", "Time to fully process a ticket, including drafting",
                          buckets=(0.05, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 40), registry=REGISTRY)
CONFIDENCE = Histogram("triage_intent_confidence", "Stated intent confidence",
                       buckets=(0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0), registry=REGISTRY)


def record(result: TicketResult) -> None:
    rule = result.rule.split(":")[0]
    TICKETS.labels(action=result.action, rule=rule).inc()
    if result.classification:
        INTENTS.labels(intent=result.classification.intent, urgency=result.classification.urgency).inc()
        CONFIDENCE.observe(result.classification.intent_confidence)
    if result.blocked_by_guardrails:
        for check, verdict in result.guardrails.items():
            if verdict != "pass":
                GUARDRAIL_BLOCKS.labels(check=check).inc()
    if result.generation_failed:
        GENERATION_FAILURES.labels(reason=result.rule.partition(":")[2] or "unknown").inc()
    if result.pii_types:
        PII_DETECTIONS.inc()
    if result.error:
        STAGE_ERRORS.inc()
    if result.cached:
        CACHE_HITS.inc()
    TRIAGE_SECONDS.observe(result.triage_ms / 1000)
    TOTAL_SECONDS.observe(result.total_ms / 1000)


def render() -> bytes:
    """Current metrics in the Prometheus text format."""
    return generate_latest(REGISTRY)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args(argv)
    start_http_server(args.port, registry=REGISTRY)
    print(f"serving metrics on http://localhost:{args.port}/metrics (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
