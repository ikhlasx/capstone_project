"""Relevance-threshold sweep for retrieval, run on the DEVELOPMENT set only.

For each candidate threshold it reports:
- hit@k:        share of tickets that have expected docs where at least one expected doc is in
                the top-k results at or above the threshold
- top-1 correct: share of those tickets where the single best passage clears the threshold and
                comes from an expected doc
- correct empty: share of tickets with NO expected docs that get no passage above the threshold
                (the "return nothing rather than something irrelevant" requirement)
- hit@k split by language fluency (fairness check: retrieval often degrades on non-fluent text)

It does not choose the threshold. The student reads the trade-off and records the choice
and the reasoning in the PRD.

Usage:  python -m evaluation.retrieval_sweep --input data/development_tickets.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from src.config import get_settings
from src.ingest import load_tickets
from src.retrieve import Retriever, SentenceTransformerEmbedder

THRESHOLDS = [round(0.20 + 0.05 * i, 2) for i in range(11)]  # 0.20 … 0.70


def pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def sweep(rows: list[dict], thresholds: list[float]) -> list[dict]:
    """rows: [{expected: set, fluency: str, passages: [(doc_id, score), ...]}]"""
    out = []
    for t in thresholds:
        hit = top1 = n_ans = empty_ok = n_none = 0
        by_flu = defaultdict(lambda: [0, 0])
        for r in rows:
            kept = [(d, s) for d, s in r["passages"] if s >= t]
            if r["expected"]:
                n_ans += 1
                h = any(d in r["expected"] for d, _ in kept)
                hit += h
                top1 += bool(kept) and kept[0][0] in r["expected"]
                by_flu[r["fluency"]][0] += h
                by_flu[r["fluency"]][1] += 1
            else:
                n_none += 1
                empty_ok += not kept
        out.append({
            "threshold": t,
            "hit_at_k": pct(hit, n_ans),
            "top1_correct": pct(top1, n_ans),
            "correct_empty": pct(empty_ok, n_none),
            "hit_at_k_by_fluency": {f: pct(a, b) for f, (a, b) in sorted(by_flu.items())},
            "n_with_docs": n_ans,
            "n_without_docs": n_none,
        })
    return out


def to_markdown(result: dict) -> str:
    lines = [f"# Retrieval threshold sweep ({result['label']})", "",
             f"Input: `{result['input']}` · tickets: {result['tickets']} · top-k: {result['top_k']} · "
             f"embedder: `{result['embedder']}`", "",
             "Development data only. The threshold choice and its justification belong in the PRD.", ""]
    for variant, rows in result["variants"].items():
        flus = sorted(rows[0]["hit_at_k_by_fluency"])
        lines += [f"## Query = {variant}", "",
                  "| Threshold | hit@k | top-1 correct | correct empty (no-doc tickets) | "
                  + " | ".join(f"hit@k {f}" for f in flus) + " |",
                  "|---|---|---|---|" + "---|" * len(flus)]
        for r in rows:
            lines.append(f"| {r['threshold']:.2f} | {r['hit_at_k']}% | {r['top1_correct']}% | "
                         f"{r['correct_empty']}% | "
                         + " | ".join(f"{r['hit_at_k_by_fluency'][f]}%" for f in flus) + " |")
        lines.append("")
    lines += [f"Tickets with expected docs: {result['variants'][next(iter(result['variants']))][0]['n_with_docs']}; "
              f"without: {result['variants'][next(iter(result['variants']))][0]['n_without_docs']}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="labelled tickets (development set)")
    ap.add_argument("--output-dir", default="evaluation/results")
    ap.add_argument("--top-k", type=int, default=s.retrieval_top_k)
    args = ap.parse_args(argv)

    result_in = load_tickets(args.input)
    tickets = [t for t in result_in.tickets if t.labels]
    if any(not t.ticket_id.startswith("DEV-") for t in tickets) or "hidden" in args.input.lower():
        print("Refusing: thresholds may only be tuned on the development set (DEV-* tickets).")
        return 2

    retriever = Retriever(SentenceTransformerEmbedder(s.embedding_model), s.chroma_path)
    variants = {"subject + body": lambda t: t.text, "body only": lambda t: t.body}
    out_variants = {}
    for name, q in variants.items():
        rows = []
        for t in tickets:
            ps = retriever.search(q(t), top_k=args.top_k)
            rows.append({"expected": set(t.labels.get("expected_doc_ids") or []),
                         "fluency": t.language_fluency,
                         "passages": [(p.doc_id, p.score) for p in ps]})
        out_variants[name] = sweep(rows, THRESHOLDS)

    result = {"label": "development", "input": args.input, "tickets": len(tickets),
              "top_k": args.top_k, "embedder": s.embedding_model, "variants": out_variants}
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "retrieval_sweep_dev.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "retrieval_sweep_dev.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
