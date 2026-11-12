"""Classifier calibration and routing-threshold sweep, run on the DEVELOPMENT set only.

Every prediction used here is out-of-fold (5-fold cross-validation), so no ticket is scored by a
model that saw it in training. The script reports:

1. Intent precision and recall per class, and urgency accuracy.
2. Calibration: stated confidence against observed accuracy, per confidence band.
3. A sweep of the intent-confidence threshold through the real routing rules, for several rule
   variants: share auto-answered, agreement with `expected_route`, and the number of protected
   tickets that would have been auto-answered (must be zero).
4. How the billing-dispute rule behaves on billing tickets.
5. How much identical tickets disagree in their labels, which caps achievable accuracy.

It does not choose thresholds. The student reads the trade-offs and records the choice in the PRD.

Usage:  python -m evaluation.threshold_sweep --input data/development_tickets.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from src.classify import TicketClassifier, make_intent_head, make_urgency_head, to_classification
from src.config import get_settings
from src.ingest import load_tickets
from src.retrieve import Retriever, SentenceTransformerEmbedder
from src.route import BILLING_INTENT, RoutingConfig, is_billing_dispute, route

CONF_THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(14)]  # 0.30 … 0.95


def calibration(conf: np.ndarray, correct: np.ndarray, bins: int = 5) -> dict:
    edges = np.linspace(0, 1, bins + 1)
    rows, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.sum():
            acc, mc = float(correct[m].mean()), float(conf[m].mean())
            ece += m.sum() / len(conf) * abs(acc - mc)
            rows.append({"band": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                         "mean_confidence": round(100 * mc, 1), "accuracy": round(100 * acc, 1)})
    return {"bands": rows, "ece_points": round(100 * ece, 1),
            "mean_confidence": round(100 * float(conf.mean()), 1),
            "accuracy": round(100 * float(correct.mean()), 1),
            "gap_points": round(100 * abs(float(conf.mean()) - float(correct.mean())), 1)}


def simulate(tickets, classifications, passages, cfg: RoutingConfig) -> dict:
    auto = agree = unsafe = missed = over = 0
    rules = Counter()
    for t, c, ps in zip(tickets, classifications, passages):
        d = route(t, c, ps, cfg)
        rules[d.rule] += 1
        got = "auto_respond" if d.action == "generate" else "escalate"
        want = t.labels["expected_route"]
        auto += got == "auto_respond"
        agree += got == want
        unsafe += got == "auto_respond" and bool(t.labels.get("must_not_auto_respond"))
        missed += got == "auto_respond" and want == "escalate"
        over += got == "escalate" and want == "auto_respond"
    n = len(tickets)
    return {"auto_rate": round(100 * auto / n, 1), "route_agreement": round(100 * agree / n, 1),
            "unsafe_auto": unsafe, "auto_but_should_escalate": missed,
            "escalated_but_answerable": over, "rules": dict(rules)}


def label_disagreement(tickets) -> dict:
    groups = defaultdict(list)
    for t in tickets:
        groups[(t.subject.lower(), t.body.lower())].append(t)
    dups = [g for g in groups.values() if len(g) > 1]
    out = {"duplicate_groups": len(dups), "tickets_in_groups": sum(map(len, dups))}
    for key in ("intent", "urgency", "answerable_from_docs", "expected_route"):
        out[f"groups_conflicting_{key}"] = sum(1 for g in dups if len({str(t.labels[key]) for t in g}) > 1)
    return out


def to_markdown(r: dict) -> str:
    L = [f"# Classifier and routing sweep ({r['label']})", "",
         f"Input: `{r['input']}` · tickets: {r['tickets']} · embedder: `{r['embedder']}` · "
         f"all predictions out-of-fold (5-fold). Development data only.", "",
         "## 1. Classification", "",
         f"- Intent accuracy: **{r['intent']['accuracy']}%**, macro precision "
         f"**{r['intent']['macro_precision']}%**, macro recall **{r['intent']['macro_recall']}%** (target: precision ≥ 85%)",
         f"- Urgency accuracy: **{r['urgency']['accuracy']}%** (always guessing the most common level "
         f"would score {r['urgency']['majority_baseline']}%)", "",
         "| Intent | Precision | Recall | Tickets |", "|---|---|---|---|"]
    L += [f"| {k} | {v['precision']}% | {v['recall']}% | {v['n']} |" for k, v in r["intent"]["per_class"].items()]
    L += ["", "| Urgency | Precision | Recall | Tickets |", "|---|---|---|---|"]
    L += [f"| {k} | {v['precision']}% | {v['recall']}% | {v['n']} |" for k, v in r["urgency"]["per_class"].items()]
    for name in ("intent", "urgency"):
        c = r[name]["calibration"]
        L += ["", f"## 2. Calibration: {name}", "",
              f"Mean stated confidence {c['mean_confidence']}% vs accuracy {c['accuracy']}% "
              f"(gap **{c['gap_points']} points**; condition: within 5). Expected calibration error: {c['ece_points']} points.", "",
              "| Confidence band | Tickets | Mean confidence | Accuracy |", "|---|---|---|---|"]
        L += [f"| {b['band']} | {b['n']} | {b['mean_confidence']}% | {b['accuracy']}% |" for b in c["bands"]]
    L += ["", "## 3. Routing sweep over the intent-confidence threshold", "",
          f"Relevance threshold fixed at {r['relevance_threshold']}. \"Agreement\" is with the `expected_route` label.", ""]
    for variant, rows in r["routing"].items():
        L += [f"### {variant}", "",
              "| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | "
              "Auto but should escalate | Escalated but answerable |", "|---|---|---|---|---|---|"]
        L += [f"| {row['threshold']:.2f} | {row['auto_rate']}% | {row['route_agreement']}% | {row['unsafe_auto']} | "
              f"{row['auto_but_should_escalate']} | {row['escalated_but_answerable']} |" for row in rows]
        L.append("")
    L += [f"Rules fired at confidence {r['default_threshold']} (default variant): `{r['rules_at_default']}`", "",
          "## 4. Billing-dispute rule on billing tickets", "",
          "| Rule says dispute | Label says escalate | Tickets |", "|---|---|---|"]
    L += [f"| {k.split('|')[0]} | {k.split('|')[1]} | {v} |" for k, v in sorted(r["billing_dispute"].items())]
    d = r["label_disagreement"]
    L += ["", "## 5. Identical tickets with different labels", "",
          f"{d['tickets_in_groups']} tickets fall into {d['duplicate_groups']} groups that share the exact same subject and body.",
          f"Groups whose members disagree: intent {d['groups_conflicting_intent']}, urgency {d['groups_conflicting_urgency']}, "
          f"answerable {d['groups_conflicting_answerable_from_docs']}, expected route {d['groups_conflicting_expected_route']}.",
          "No text-based system can predict a label that differs between identical tickets, so these counts cap achievable accuracy.", "",
          f"Reference point: routing every non-protected ticket to auto-answer using the *true* intent would agree with "
          f"`expected_route` on **{r['oracle_agreement']}%** of tickets.", ""]
    return "\n".join(L)


def per_class(y_true, y_pred) -> dict:
    labels = sorted(set(y_true))
    p, rc, _, n = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    return {l: {"precision": round(100 * float(a), 1), "recall": round(100 * float(b), 1), "n": int(c)}
            for l, a, b, c in zip(labels, p, rc, n)}


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="labelled tickets (development set)")
    ap.add_argument("--output-dir", default="evaluation/results")
    args = ap.parse_args(argv)

    tickets = [t for t in load_tickets(args.input).tickets if t.labels and not t.is_empty]
    if any(not t.ticket_id.startswith("DEV-") for t in tickets) or "hidden" in args.input.lower():
        print("Refusing: thresholds may only be tuned on the development set (DEV-* tickets).")
        return 2

    embedder = SentenceTransformerEmbedder(s.embedding_model)
    X = np.asarray(embedder.encode([t.text for t in tickets]))
    y_int = np.array([t.labels["intent"] for t in tickets])
    y_urg = np.array([t.labels["urgency"] for t in tickets])
    skf = StratifiedKFold(5, shuffle=True, random_state=0)
    P_int = cross_val_predict(make_intent_head(), X, y_int, cv=skf, method="predict_proba")
    P_urg = cross_val_predict(make_urgency_head(), X, y_urg, cv=skf, method="predict_proba")
    int_classes, urg_classes = sorted(set(y_int)), sorted(set(y_urg))
    cls = [to_classification(int_classes, P_int[i], urg_classes, P_urg[i],
                             TicketClassifier.MODEL_NAME, "out-of-fold") for i in range(len(tickets))]

    pred_int = np.array([c.intent for c in cls]); pred_urg = np.array([c.urgency for c in cls])
    pi = per_class(y_int, pred_int)
    result = {
        "label": "development", "input": args.input, "tickets": len(tickets), "embedder": s.embedding_model,
        "intent": {"accuracy": round(100 * float((pred_int == y_int).mean()), 1),
                   "macro_precision": round(float(np.mean([v["precision"] for v in pi.values()])), 1),
                   "macro_recall": round(float(np.mean([v["recall"] for v in pi.values()])), 1),
                   "per_class": pi,
                   "calibration": calibration(np.array([c.intent_confidence for c in cls]), pred_int == y_int)},
        "urgency": {"accuracy": round(100 * float((pred_urg == y_urg).mean()), 1),
                    "majority_baseline": round(100 * Counter(y_urg).most_common(1)[0][1] / len(y_urg), 1),
                    "per_class": per_class(y_urg, pred_urg),
                    "calibration": calibration(np.array([c.urgency_confidence for c in cls]), pred_urg == y_urg)},
    }

    retriever = Retriever(embedder, s.chroma_path)
    passages = [retriever.search(t.text, top_k=s.retrieval_top_k) for t in tickets]
    rel = s.relevance_threshold
    variants = {
        "default (dispute + residency rules on, incident rule off)": {},
        "incident rule on": {"incident_rule": True},
        "dispute rule off": {"dispute_rule": False},
        "residency rule off": {"residency_rule": False},
        "no protected-margin rule": {"protected_margin": 2.0},
    }
    result["relevance_threshold"] = rel
    result["routing"] = {
        name: [{"threshold": th, **{k: v for k, v in simulate(
            tickets, cls, passages, RoutingConfig(confidence_threshold=th, relevance_threshold=rel, **kw)).items()
            if k != "rules"}} for th in CONF_THRESHOLDS]
        for name, kw in variants.items()}
    result["default_threshold"] = s.confidence_threshold
    result["rules_at_default"] = simulate(tickets, cls, passages, RoutingConfig(
        confidence_threshold=s.confidence_threshold, relevance_threshold=rel))["rules"]

    bd = Counter()
    for t in tickets:
        if t.labels["intent"] == BILLING_INTENT:
            bd[f"{'yes' if is_billing_dispute(t) else 'no'}|{'yes' if t.labels['expected_route'] == 'escalate' else 'no'}"] += 1
    result["billing_dispute"] = dict(bd)
    result["label_disagreement"] = label_disagreement(tickets)
    from src.route import ALWAYS_ESCALATE
    result["oracle_agreement"] = round(100 * sum(
        ("escalate" if t.labels["intent"] in ALWAYS_ESCALATE else "auto_respond") == t.labels["expected_route"]
        for t in tickets) / len(tickets), 1)

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "classifier_sweep_dev.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "classifier_sweep_dev.md").write_text(to_markdown(result), encoding="utf-8")
    print(to_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
