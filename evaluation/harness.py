"""Run a whole ticket file through the pipeline, unattended, and write a metrics report (A9, A10).

Usage:
    python -m evaluation.harness --input PATH_TO_TICKETS.json --output OUTPUT_DIR
        [--ground-truth PATH]   expert reference answers, for answer-quality metrics
        [--provider auto|stub]  'stub' runs without an API key (used by CI)
        [--limit N]             process only the first N tickets

Outputs in OUTPUT_DIR:
    metrics.json, metrics.md     the report
    results.jsonl                one line per ticket: action, reason, reply or escalation packet
    escalation_queue.json        escalated tickets ordered by urgency, then age
    decisions.db                 the decision log for this run

No ticket can stop the run: the pipeline escalates on any failure, and anything that still
escapes is caught here and recorded as an escalation.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from evaluation.metrics import compute_metrics, to_markdown
from src.config import get_settings
from src.generate import StubProvider
from src.ingest import load_tickets
from src.models import IngestError, Ticket
from src.pipeline import EscalationPacket, Pipeline, TicketResult, build_pipeline, sort_escalations, summarise


def infer_label(tickets: list[Ticket], path: str) -> str:
    prefixes = {t.ticket_id.split("-")[0] for t in tickets}
    if prefixes == {"DEV"}:
        return "development"
    if prefixes == {"VAL"}:
        return "validation"
    return "hidden/unlabelled" if not any(t.labels for t in tickets) else Path(path).stem


def emergency_escalation(ticket: Ticket, exc: Exception) -> TicketResult:
    reason = f"Unexpected error while processing ({type(exc).__name__}); a person must handle this ticket."
    return TicketResult(
        ticket_id=ticket.ticket_id, action="escalate", rule="internal_error", reason=reason, error=type(exc).__name__,
        packet=EscalationPacket(ticket_id=ticket.ticket_id, channel=ticket.channel.value, received_at=ticket.received_at,
                                customer_tier=ticket.customer_tier, summary=summarise(ticket, None),
                                likely_intent="unknown", intent_confidence=0.0, urgency="medium",
                                reason=reason, rule="internal_error", unsure_about="",
                                ingest_warnings=list(ticket.ingest_warnings)))


def load_ground_truth(path: str | None) -> dict[str, dict] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return {g["ticket_id"]: g for g in data if isinstance(g, dict) and g.get("ticket_id")}


def run(input_path: str, output_dir: str, pipeline_factory: Callable[[str, str], Pipeline],
        ground_truth_path: str | None = None, limit: int | None = None, meta: dict | None = None,
        progress: Callable[[str], None] = print) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    ingested = load_tickets(input_path)          # raises IngestError for an unreadable file
    tickets = ingested.tickets[:limit] if limit else ingested.tickets
    pipeline = pipeline_factory(str(out / "decisions.db"), run_id)

    rows: list[tuple[Ticket, TicketResult]] = []
    t0 = time.perf_counter()
    for i, ticket in enumerate(tickets, start=1):
        try:
            result = pipeline.process(ticket)
        except Exception as exc:                 # last line of defence; the pipeline should never raise
            result = emergency_escalation(ticket, exc)
        rows.append((ticket, result))
        if i % 20 == 0 or i == len(tickets):
            progress(f"  {i}/{len(tickets)} tickets  ({time.perf_counter() - t0:.0f}s)")

    with (out / "results.jsonl").open("w", encoding="utf-8") as fh:
        for _, r in rows:
            fh.write(r.model_dump_json(exclude={"passages": {"__all__": {"text"}}}) + "\n")

    queue = sort_escalations([r.packet for _, r in rows if r.packet])
    (out / "escalation_queue.json").write_text(
        json.dumps([p.model_dump(mode="json") for p in queue], indent=2, ensure_ascii=False), encoding="utf-8")

    metrics = compute_metrics(rows, pipeline.log.tickets_by_stage(), ingest_errors=len(ingested.errors),
                              ground_truth=load_ground_truth(ground_truth_path))
    info = {"label": infer_label(tickets, input_path), "input": input_path, "run_id": run_id,
            "started_at": started_at, "wall_seconds": round(time.perf_counter() - t0, 1),
            "confidence_threshold": pipeline.routing.confidence_threshold,
            "relevance_threshold": pipeline.routing.relevance_threshold,
            "provider": pipeline.generator.provider.name if pipeline.generator else "none (no API key)",
            "model": pipeline.generator.model if pipeline.generator else "none", **(meta or {})}
    report = {"meta": info, **metrics}
    (out / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "metrics.md").write_text(to_markdown(metrics, info), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="ticket file (.json list, {'tickets': [...]} or .jsonl)")
    ap.add_argument("--output", required=True, help="directory for the report and run outputs")
    ap.add_argument("--ground-truth", default=None, help="reference answers (optional)")
    ap.add_argument("--provider", choices=["auto", "stub"], default="auto")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)

    settings = get_settings()
    provider = StubProvider() if args.provider == "stub" else "auto"

    def factory(db_path: str, run_id: str) -> Pipeline:
        return build_pipeline(settings, database_url=db_path, run_id=run_id, provider=provider)

    try:
        report = run(args.input, args.output, factory, args.ground_truth, args.limit)
    except IngestError as exc:
        print(f"Cannot read the input: {exc}")
        return 2

    v, g = report["volume"], report["governance"]
    print(f"\n{report['meta']['label']}: processed {v['processed']} | auto-answered {v['auto_answered']} | "
          f"escalated {v['escalated']} (guardrail blocks {v['blocked_by_guardrails']}, drafting failures {v['generation_failed']})")
    if report.get("safety"):
        print(f"auto-replies on protected tickets: {report['safety']['auto_responses_on_protected_tickets']}")
    print(f"decision log reconciles: {'yes' if g['reconciles'] else 'NO'}")
    print(f"report: {Path(args.output) / 'metrics.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
