"""Build the human-review sheets: a sample of automated replies for two reviewers to judge.

    python -m evaluation.human_review.make_review_sheets \
        --results evaluation/results/validation/results.jsonl \
        --tickets data/validation_tickets.json [--n 50] [--seed 7]

Writes reviewer_A.csv and reviewer_B.csv (identical content, opened in Excel or Sheets) plus
sample.json. Each row holds the ticket, the reply that was sent, and the full text of every passage
it cites, so a reviewer can judge it without opening anything else. Reviewers fill in the
three answer columns independently, without seeing each other's sheet. See RUBRIC.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from src.chunking import chunk_corpus, load_corpus
from src.config import get_settings
from src.ingest import load_tickets

HERE = Path(__file__).resolve().parent
ANSWER_COLUMNS = ["unsupported_claim (yes/no)", "citations_support (all/some/none)", "would_send (yes/no)", "notes"]


def stratified_sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    """Spread the sample across intents, so common intents do not crowd out the rest."""
    rng = random.Random(seed)
    by_intent = defaultdict(list)
    for r in rows:
        by_intent[r["classification"]["intent"]].append(r)
    for group in by_intent.values():
        rng.shuffle(group)
    picked, intents = [], sorted(by_intent)
    while len(picked) < min(n, len(rows)):
        for intent in intents:
            if by_intent[intent] and len(picked) < n:
                picked.append(by_intent[intent].pop())
    rng.shuffle(picked)
    return picked


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="results.jsonl from a harness run")
    ap.add_argument("--tickets", required=True, help="the ticket file that run processed")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE))
    args = ap.parse_args(argv)

    results = [json.loads(l) for l in Path(args.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    replies = [r for r in results if r["action"] == "auto_respond" and r.get("reply")]
    tickets = {t.ticket_id: t for t in load_tickets(args.tickets).tickets}
    chunks = {c.chunk_id: c for c in chunk_corpus(load_corpus(s.docs_path))}
    sample = stratified_sample(replies, args.n, args.seed)
    if len(sample) < args.n:
        print(f"Note: only {len(sample)} automated replies are available; the Evaluation Framework asks for at least 50. "
              "Add replies from another run (for example the development run) to reach 50.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    header = ["item", "ticket_id", "intent", "ticket", "reply_sent", "cited_passages"] + ANSWER_COLUMNS
    records = []
    for i, r in enumerate(sample, start=1):
        t = tickets.get(r["ticket_id"])
        cited = "\n\n".join(f"[{cid}] {chunks[cid].title} — {chunks[cid].section}\n{chunks[cid].text}"
                            for cid in r["citations"] if cid in chunks)
        records.append({"item": i, "ticket_id": r["ticket_id"], "intent": r["classification"]["intent"],
                        "ticket": t.text if t else "(ticket not found)", "reply_sent": r["reply"],
                        "cited_passages": cited or "(no citations)"})
    for reviewer in ("A", "B"):
        with (out / f"reviewer_{reviewer}.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=header)
            w.writeheader()
            for rec in records:
                w.writerow({**rec, **{c: "" for c in ANSWER_COLUMNS}})
    (out / "sample.json").write_text(json.dumps({"results": args.results, "tickets": args.tickets, "seed": args.seed,
                                                 "items": [{"item": r["item"], "ticket_id": r["ticket_id"]} for r in records]},
                                                indent=2), encoding="utf-8")
    intents = len({r["intent"] for r in records})
    print(f"wrote {len(records)} items across {intents} intents to {out / 'reviewer_A.csv'} and reviewer_B.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
