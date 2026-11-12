"""Readable demonstrations of the system, for walkthroughs and the project video.

    python -m scripts.demo ticket "my deployment keeps dying at the container health check phase"
    python -m scripts.demo ticket "Our auditor requires access logs for the last six months" --subject "Audit request" --channel email
    python -m scripts.demo guardrail
    python -m scripts.demo log DEMO-01

`ticket` sends one ticket through the real pipeline and prints each decision in plain words.
`guardrail` runs real drafts that break the rules through the real guardrail checks and shows
them being blocked.
`log` prints the decision-log rows for a ticket from its most recent run.

Demo tickets are logged to the normal decision log (DATABASE_URL), under run ids starting "demo-".
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import textwrap
import uuid

from src.config import get_settings

LINE = "-" * 78


def wrap(text: str, indent: str = "    ") -> str:
    return "\n".join(textwrap.fill(p, 78, initial_indent=indent, subsequent_indent=indent) if p.strip() else ""
                     for p in text.split("\n"))


def cmd_ticket(args) -> int:
    from src.ingest import normalise_record
    from src.pipeline import build_pipeline

    s = get_settings()
    print("Loading the pipeline (embedding model, index, classifier)...")
    pipeline = build_pipeline(s, database_url=s.database_url, run_id=f"demo-{uuid.uuid4().hex[:6]}")
    ticket = normalise_record({"ticket_id": args.id, "channel": args.channel, "subject": args.subject, "body": args.text})
    r = pipeline.process(ticket)
    c = r.classification

    print(LINE, f"TICKET {ticket.ticket_id}  ({ticket.channel.value})", LINE, sep="\n")
    print(wrap(ticket.text))
    print(LINE)
    print(f"1. CLASSIFY   intent = {c.intent}  (confidence {c.intent_confidence:.2f}),  urgency = {c.urgency}")
    print(f"              next guesses: " + ", ".join(f"{a.value} {a.confidence:.2f}" for a in c.alternatives))
    print("2. RETRIEVE   passages above the relevance threshold "
          f"({pipeline.routing.relevance_threshold:.2f}):")
    for p in r.passages[:3] or []:
        print(f"              {p.score:.2f}  {p.chunk_id}  ({p.title})")
    if not r.passages:
        print("              none")
    print(f"3. ROUTE      rule = {r.rule.split(':')[0]}")
    print(wrap(r.reason, "              "))
    if r.action == "auto_respond":
        print("4. GENERATE   draft written from the passages, citing: " + ", ".join(r.citations))
        print("5. VALIDATE   " + ", ".join(f"{k} {v}" for k, v in r.guardrails.items()))
        print(f"6. ACT        AUTO-REPLY SENT   ({r.total_ms / 1000:.2f} s{', answer from cache' if r.cached else ''})")
        print(LINE, "THE REPLY THE CUSTOMER RECEIVES", LINE, sep="\n")
        print(wrap(r.reply))
    else:
        k = r.packet
        print(f"4. ACT        ESCALATED TO A PERSON   ({r.total_ms / 1000:.2f} s)")
        if k.guardrail_failures:
            print("              guardrails blocked a draft: " + ", ".join(k.guardrail_failures))
        print(LINE, "THE CONTEXT PACKET THE AGENT RECEIVES", LINE, sep="\n")
        print(f"    summary:      {k.summary}")
        print(f"    likely intent {k.likely_intent} ({k.intent_confidence:.2f}),  urgency {k.urgency}")
        print(f"    reason:       {k.reason}")
        if k.unsure_about:
            print(f"    unsure about: {k.unsure_about}")
        print("    articles attached: " + (", ".join(p["chunk_id"] for p in k.retrieved) or "none"))
    print(LINE)
    print(f"Logged as run {pipeline.log.run_id}. See it with:  python -m scripts.demo log {ticket.ticket_id}")
    return 0


GUARDRAIL_CASES = [
    ("A refund promise and 'fixed on our side'",
     "We have fixed the issue on our side and a refund has been issued to your card [{c}]."),
    ("Private data in the reply",
     "Please email our engineer at jane.doe@cloudserve.example and follow the steps in the article [{c}]."),
    ("A citation to an article that was never retrieved",
     "Follow the steps in the scaling guide and the problem will go away [DOC-PERF-002#resolution]."),
    ("A fix date",
     "Our engineers are aware of this and a fix will be deployed within 2 days [{c}]."),
]


def cmd_guardrail(args) -> int:
    from src.generate import Draft
    from src.guardrails import validate
    from src.ingest import normalise_record
    from src.retrieve import Passage

    ticket = normalise_record({"ticket_id": "DEMO-G", "channel": "chat",
                               "body": "My deployment keeps failing at the health check stage. What should I do?"})
    passages = [Passage(chunk_id="DOC-DEPLOY-001#resolution", doc_id="DOC-DEPLOY-001",
                        title="Container deployments failing during the health check phase", section="Resolution",
                        text="Confirm the container listens on the declared port...", score=0.81)]
    print("Each draft below is checked by the same guardrail code the pipeline runs on every answer.")
    print("Retrieved for this ticket: DOC-DEPLOY-001#resolution\n")
    for title, answer in GUARDRAIL_CASES:
        draft = Draft(can_answer=True, answer=answer.format(c="DOC-DEPLOY-001#resolution"),
                      citations=tuple(x for x in ["DOC-DEPLOY-001#resolution"] if x in answer.format(c=x)) or ("DOC-PERF-002#resolution",),
                      unsure_about="", model="demo", prompt_version="PR-01@1.0")
        report = validate(ticket, draft, passages)
        print(LINE, f"{title}", LINE, sep="\n")
        print(wrap(draft.answer))
        verdict = "BLOCKED" if not report.passed else "PASSED"
        print(f"\n    {verdict}" + (" by: " + "; ".join(f"{k} ({report.results[k]})" for k in report.blocked_by) if not report.passed else ""))
        print()

    clean = Draft(can_answer=True, citations=("DOC-DEPLOY-001#resolution",), unsure_about="", model="demo",
                  prompt_version="PR-01@1.0",
                  answer="Confirm that the container is listening on the port declared in the service definition "
                         "[DOC-DEPLOY-001#resolution].")
    print(LINE, "For comparison, a clean grounded draft", LINE, sep="\n")
    print(wrap(clean.answer))
    print("\n    " + ("PASSED all checks" if validate(ticket, clean, passages).passed else "BLOCKED"))
    print("\nA blocked draft is never sent. The ticket is escalated, and the failed checks are recorded in the log.")
    return 0


def cmd_log(args) -> int:
    from src.logging_store import sqlite_path

    s = get_settings()
    conn = sqlite3.connect(sqlite_path(args.db or s.database_url))
    row = conn.execute("SELECT run_id FROM decisions WHERE ticket_id = ? ORDER BY timestamp DESC LIMIT 1",
                       (args.ticket_id,)).fetchone()
    if not row:
        print(f"No decisions logged for {args.ticket_id}.")
        return 1
    rows = conn.execute("SELECT timestamp, stage, action_taken, prediction, reason, requirement_ids, prompt_version "
                        "FROM decisions WHERE ticket_id = ? AND run_id = ? ORDER BY timestamp, rowid",
                        (args.ticket_id, row[0])).fetchall()
    print(f"Decision log for {args.ticket_id}, run {row[0]}: {len(rows)} rows\n")
    for ts, stage, action, pred, reason, reqs, pv in rows:
        p = json.loads(pred)
        print(f"  {ts[11:19]}  {stage:<15} action={action:<13} prediction={p.get('value')}"
              + (f" ({p['confidence']:.2f})" if isinstance(p.get("confidence"), (int, float)) else ""))
        print(f"            reason: {reason[:90]}")
        print(f"            requirements: {', '.join(json.loads(reqs))}" + (f"   prompt: {pv}" if pv else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("ticket", help="run one ticket through the pipeline")
    t.add_argument("text")
    t.add_argument("--subject", default="")
    t.add_argument("--channel", default="chat")
    t.add_argument("--id", default="DEMO-01")
    sub.add_parser("guardrail", help="show the guardrails blocking bad drafts")
    l = sub.add_parser("log", help="show the decision log for a ticket")
    l.add_argument("ticket_id")
    l.add_argument("--db", default=None)
    args = ap.parse_args(argv)
    return {"ticket": cmd_ticket, "guardrail": cmd_guardrail, "log": cmd_log}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
