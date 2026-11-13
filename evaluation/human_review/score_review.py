"""Score the completed human-review sheets.

    python -m evaluation.human_review.score_review \
        --a evaluation/human_review/reviewer_A.csv --b evaluation/human_review/reviewer_B.csv

Reports, for each reviewer and for the two combined:
- hallucination rate: share of replies with at least one claim not supported by the cited passages
- citation accuracy: share of replies whose citations all support the sentences they are attached to
- would-send rate: share of replies a reviewer would have sent unchanged
and, for each question, the agreement between reviewers (percent agreement and Cohen's kappa),
plus the list of items they disagreed on, for a discussion that settles each one.
Writes review_results.md next to the sheets.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

QUESTIONS = {
    "unsupported_claim (yes/no)": ("unsupported claim", {"yes", "no"}),
    "citations_support (all/some/none)": ("citations support", {"all", "some", "none"}),
    "would_send (yes/no)": ("would send", {"yes", "no"}),
}


def read(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        for col, (_, allowed) in QUESTIONS.items():
            v = (r.get(col) or "").strip().lower()
            if v not in allowed:
                raise SystemExit(f"{path}, item {r['item']}: '{col}' must be one of {sorted(allowed)}, got '{v}'")
            r[col] = v
        out[r["item"]] = r
    return out


def kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / (n * n)
    return round((po - pe) / (1 - pe), 2) if pe < 1 else 1.0


def pct(x: int, n: int) -> str:
    return f"{100 * x / n:.1f}%" if n else "n/a"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    A, B = read(args.a), read(args.b)
    items = sorted(set(A) & set(B), key=int)
    if set(A) != set(B):
        print(f"Warning: the sheets cover different items; scoring the {len(items)} they share.")
    n = len(items)

    def rate(sheet, col, value):
        return sum(sheet[i][col] == value for i in items)

    L = [f"# Human review results", "", f"Replies reviewed: **{n}** · reviewers: 2, working independently", "",
         "| Measure | Reviewer A | Reviewer B | Either reviewer | Both reviewers |", "|---|---|---|---|---|"]
    col = "unsupported_claim (yes/no)"
    hal_either = sum(A[i][col] == "yes" or B[i][col] == "yes" for i in items)
    hal_both = sum(A[i][col] == "yes" and B[i][col] == "yes" for i in items)
    L.append(f"| Hallucination rate (≥1 unsupported claim; target ≤ 5%) | {pct(rate(A, col, 'yes'), n)} | "
             f"{pct(rate(B, col, 'yes'), n)} | {pct(hal_either, n)} | {pct(hal_both, n)} |")
    col = "citations_support (all/some/none)"
    cit_both = sum(A[i][col] == "all" and B[i][col] == "all" for i in items)
    cit_either = sum(A[i][col] == "all" or B[i][col] == "all" for i in items)
    L.append(f"| Citation accuracy (all citations support their sentence; target ≥ 95%) | {pct(rate(A, col, 'all'), n)} | "
             f"{pct(rate(B, col, 'all'), n)} | {pct(cit_either, n)} | {pct(cit_both, n)} |")
    col = "would_send (yes/no)"
    L.append(f"| Would send unchanged | {pct(rate(A, col, 'yes'), n)} | {pct(rate(B, col, 'yes'), n)} | "
             f"{pct(sum(A[i][col] == 'yes' or B[i][col] == 'yes' for i in items), n)} | "
             f"{pct(sum(A[i][col] == 'yes' and B[i][col] == 'yes' for i in items), n)} |")
    L += ["", "\"Either\" is the cautious reading for hallucination (a reply counts if either reviewer flagged it).", "",
          "## Agreement between reviewers", "", "| Question | Percent agreement | Cohen's kappa |", "|---|---|---|"]
    disagreements = []
    for col, (label, _) in QUESTIONS.items():
        a, b = [A[i][col] for i in items], [B[i][col] for i in items]
        L.append(f"| {label} | {pct(sum(x == y for x, y in zip(a, b)), n)} | {kappa(a, b)} |")
        disagreements += [(i, label, A[i][col], B[i][col]) for i in items if A[i][col] != B[i][col]]
    L += ["", "Kappa above 0.6 is usually read as substantial agreement; below 0.4 means the rubric needs tightening.", "",
          "## Items the reviewers disagreed on", ""]
    if disagreements:
        L += ["| Item | Ticket | Question | Reviewer A | Reviewer B |", "|---|---|---|---|---|"]
        L += [f"| {i} | {A[i]['ticket_id']} | {q} | {x} | {y} |" for i, q, x, y in disagreements]
        L += ["", "Discuss each one, agree a final verdict, and record how many were resolved each way."]
    else:
        L.append("None.")
    out = Path(args.out) if args.out else Path(args.a).parent / "review_results.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
