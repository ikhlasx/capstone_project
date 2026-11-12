"""Metrics for a harness run (A10). Pure functions over (ticket, result) pairs, so they are testable.

Metrics that need labels (routing agreement, precision/recall, retrieval hit rate, the safety
count) are computed only when the input carries labels. A hidden set without labels still gets
volume, latency, governance and guardrail figures.
"""
from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict
from typing import Any, Sequence

from src.models import Ticket
from src.pipeline import TicketResult

FAIRNESS_GAP_POINTS = 5.0
GROUP_FIELDS = {"tier": "customer_tier", "region": "customer_region", "fluency": "language_fluency"}


def pct(a: float, b: float) -> float | None:
    return round(100 * a / b, 1) if b else None


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def retrieval_hit(t: Ticket, r: TicketResult) -> bool | None:
    expected = set((t.labels or {}).get("expected_doc_ids") or [])
    if not expected:
        return None
    return any(p.doc_id in expected for p in r.passages)


def per_class(pairs: list[tuple[str, str]]) -> dict[str, dict[str, Any]]:
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    out = {}
    for l in labels:
        tp = sum(a == l and b == l for a, b in pairs)
        fp = sum(a != l and b == l for a, b in pairs)
        fn = sum(a == l and b != l for a, b in pairs)
        out[l] = {"precision": pct(tp, tp + fp), "recall": pct(tp, tp + fn), "n": tp + fn}
    return out


def group_metrics(rows: list[tuple[Ticket, TicketResult]]) -> dict[str, Any]:
    n = len(rows)
    labelled = [(t, r) for t, r in rows if t.labels and t.labels.get("expected_route")]
    hits = [h for h in (retrieval_hit(t, r) for t, r in rows) if h is not None]
    return {
        "n": n,
        "auto_rate": pct(sum(r.action == "auto_respond" for _, r in rows), n),
        "route_agreement": pct(sum(r.action == t.labels["expected_route"] for t, r in labelled), len(labelled)),
        "retrieval_hit_rate": pct(sum(hits), len(hits)),
        "guardrail_block_rate": pct(sum(r.blocked_by_guardrails for _, r in rows), n),
    }


def fairness(rows: list[tuple[Ticket, TicketResult]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, field in GROUP_FIELDS.items():
        groups = defaultdict(list)
        for t, r in rows:
            groups[getattr(t, field)].append((t, r))
        table = {g: group_metrics(v) for g, v in sorted(groups.items())}
        gaps = {}
        for metric in ("auto_rate", "route_agreement", "retrieval_hit_rate", "guardrail_block_rate"):
            vals = [m[metric] for m in table.values() if m[metric] is not None]
            if len(vals) >= 2:
                gap = round(max(vals) - min(vals), 1)
                gaps[metric] = {"gap_points": gap, "flag": gap > FAIRNESS_GAP_POINTS}
        out[name] = {"groups": table, "gaps": gaps}
    return out


def answer_quality(rows: list[tuple[Ticket, TicketResult]], ground_truth: dict[str, dict]) -> dict[str, Any] | None:
    """Compare automated replies with expert reference answers, where a reference exists."""
    scored = [(r, ground_truth[t.ticket_id]) for t, r in rows if r.action == "auto_respond" and t.ticket_id in ground_truth]
    if not scored:
        return None
    mention_total = mention_hit = violations = with_mentions = 0
    for r, gt in scored:
        reply = (r.reply or "").lower()
        phrases = gt.get("must_mention") or []
        if phrases:
            with_mentions += 1
            mention_total += len(phrases)
            mention_hit += sum(p.lower() in reply for p in phrases)
        violations += sum(c.lower() in reply for c in gt.get("must_not_claim") or [])
    return {"replies_with_reference": len(scored), "replies_with_must_mention": with_mentions,
            "must_mention_coverage": pct(mention_hit, mention_total),
            "must_not_claim_violations": violations}


def compute_metrics(rows: list[tuple[Ticket, TicketResult]], log_counts: dict[str, int],
                    ingest_errors: int = 0, ground_truth: dict[str, dict] | None = None) -> dict[str, Any]:
    n = len(rows)
    results = [r for _, r in rows]
    auto = [r for r in results if r.action == "auto_respond"]
    labelled = [(t, r) for t, r in rows if t.labels and t.labels.get("expected_route")]
    has_history = [(t, r) for t, r in rows if t.history]

    m: dict[str, Any] = {"volume": {
        "processed": n, "ingest_errors": ingest_errors, "auto_answered": len(auto),
        "escalated": n - len(auto),
        "blocked_by_guardrails": sum(r.blocked_by_guardrails for r in results),
        "generation_failed": sum(r.generation_failed for r in results),
        "stage_errors": sum(bool(r.error) for r in results),
        "rules": dict(Counter(r.rule.split(":")[0] for r in results).most_common()),
    }}

    total_s = [r.total_ms / 1000 for r in results]
    m["business"] = {
        "first_contact_resolution": pct(len(auto), n),
        "escalation_rate": pct(n - len(auto), n),
        "system_response_seconds": {"mean": round(st.mean(total_s), 2) if total_s else None,
                                    "median": round(st.median(total_s), 2) if total_s else None},
        "history_baseline": {
            "tickets_with_history": len(has_history),
            "first_contact_resolution": pct(sum(bool(t.history.get("first_contact_resolution")) for t, _ in has_history), len(has_history)),
            "escalation_rate": pct(sum(bool(t.history.get("escalated")) for t, _ in has_history), len(has_history)),
            "median_resolution_minutes": st.median([t.history["resolution_time_minutes"] for t, _ in has_history
                                                    if t.history.get("resolution_time_minutes") is not None]) if has_history else None,
        } if has_history else None,
    }

    m["technical"] = {
        "latency_ms": {"triage_p50": percentile([r.triage_ms for r in results], 0.5),
                       "triage_p95": percentile([r.triage_ms for r in results], 0.95),
                       "total_p50": percentile([r.total_ms for r in results], 0.5),
                       "total_p95": percentile([r.total_ms for r in results], 0.95)},
        "cached_generations": sum(r.cached for r in results),
    }
    if labelled:
        intent_pairs = [(t.labels["intent"], r.classification.intent) for t, r in labelled if r.classification]
        urg_pairs = [(t.labels["urgency"], r.classification.urgency) for t, r in labelled if r.classification]
        hits = [h for h in (retrieval_hit(t, r) for t, r in labelled) if h is not None]
        confs = [r.classification.intent_confidence for t, r in labelled if r.classification]
        acc = pct(sum(a == b for a, b in intent_pairs), len(intent_pairs))
        pc = per_class(intent_pairs)
        precisions = [v["precision"] for v in pc.values() if v["precision"] is not None]
        auto_l = [(t, r) for t, r in labelled if r.action == "auto_respond"]
        cited_expected = [any(c.split("#")[0] in set(t.labels.get("expected_doc_ids") or []) for c in r.citations)
                          for t, r in auto_l if t.labels.get("expected_doc_ids")]
        m["technical"].update({
            "intent_accuracy": acc,
            "intent_macro_precision": round(st.mean(precisions), 1) if precisions else None,
            "intent_per_class": pc,
            "urgency_accuracy": pct(sum(a == b for a, b in urg_pairs), len(urg_pairs)),
            "urgency_per_class": per_class(urg_pairs),
            "calibration": {"mean_intent_confidence": round(100 * st.mean(confs), 1) if confs else None,
                            "intent_accuracy": acc,
                            "gap_points": round(abs(100 * st.mean(confs) - acc), 1) if confs and acc is not None else None},
            "route_agreement": pct(sum(r.action == t.labels["expected_route"] for t, r in labelled), len(labelled)),
            "route_confusion": dict(Counter(f"expected {t.labels['expected_route']} -> got {r.action}" for t, r in labelled)),
            "retrieval_hit_rate": pct(sum(hits), len(hits)),
            "citations_within_retrieved": pct(sum(set(r.citations) <= {p.chunk_id for p in r.passages} for r in auto), len(auto)),
            "auto_replies_citing_an_expected_doc": pct(sum(cited_expected), len(cited_expected)),
        })
        m["safety"] = {
            "protected_tickets": sum(bool(t.labels.get("must_not_auto_respond")) for t, _ in labelled),
            "auto_responses_on_protected_tickets": sum(
                r.action == "auto_respond" and bool(t.labels.get("must_not_auto_respond")) for t, r in labelled),
        }
    else:
        m["safety"] = None

    generated = sum(r.rule in ("answerable", "guardrail_block") or r.generation_failed for r in results)
    validated = sum(r.rule in ("answerable", "guardrail_block") for r in results)
    expected_counts = {"classification": n, "routing": n, "generation": generated, "validation": validated}
    guard = Counter()
    for r in results:
        if r.blocked_by_guardrails:
            guard.update(k for k, v in r.guardrails.items() if v != "pass")
    m["governance"] = {
        "decisions_logged": {k: log_counts.get(k, 0) for k in expected_counts},
        "decisions_expected": expected_counts,
        "reconciles": all(log_counts.get(k, 0) == v for k, v in expected_counts.items()),
        "guardrail_activations": dict(guard),
        "pii_detections": sum(bool(r.pii_types) for r in results),
        "auto_replies_with_disclosure": pct(sum("automated assistant" in (r.reply or "") for r in auto), len(auto)),
        "escalations_with_complete_packet": pct(
            sum(bool(r.packet and r.packet.summary and r.packet.reason and r.packet.likely_intent and r.packet.urgency)
                for r in results if r.action == "escalate"), n - len(auto)),
    }
    m["fairness"] = fairness(rows)
    m["answer_quality"] = answer_quality(rows, ground_truth) if ground_truth else None
    return m


# --- report --------------------------------------------------------------------------------

def fmt(v: Any, suffix: str = "") -> str:
    return "n/a" if v is None else f"{v}{suffix}"


def to_markdown(m: dict[str, Any], meta: dict[str, Any]) -> str:
    v, b, t, g = m["volume"], m["business"], m["technical"], m["governance"]
    L = [f"# Metrics report: {meta['label']}", "",
         f"- Input: `{meta['input']}` ({v['processed']} tickets processed, {v['ingest_errors']} unreadable records)",
         f"- Run: `{meta['run_id']}` at {meta['started_at']} · provider: {meta['provider']} · model: `{meta['model']}`",
         f"- Thresholds: intent confidence {meta['confidence_threshold']}, retrieval relevance {meta['relevance_threshold']}",
         f"- **These are {meta['label']} figures.** Thresholds were set on development data only.", "",
         "## Volume", "",
         "| Processed | Auto-answered | Escalated | of which blocked by guardrails | of which drafting failed |", "|---|---|---|---|---|",
         f"| {v['processed']} | {v['auto_answered']} | {v['escalated']} | {v['blocked_by_guardrails']} | {v['generation_failed']} |", "",
         "Reason each ticket ended where it did: " + ", ".join(f"`{k}` {n}" for k, n in v["rules"].items()), "",
         "## Business outcomes", ""]
    h = b["history_baseline"]
    L += ["| Measure | This system | What humans did on the same tickets (history) |", "|---|---|---|",
          f"| First-contact resolution (auto-answered ÷ all) | {fmt(b['first_contact_resolution'], '%')} | {fmt(h['first_contact_resolution'], '%') if h else 'n/a'} |",
          f"| Escalation rate | {fmt(b['escalation_rate'], '%')} | {fmt(h['escalation_rate'], '%') if h else 'n/a'} |",
          f"| Response time | median {fmt(b['system_response_seconds']['median'], ' s')}, mean {fmt(b['system_response_seconds']['mean'], ' s')} (system processing time) | "
          f"median {fmt(h['median_resolution_minutes'], ' min') if h else 'n/a'} (time to resolve) |", "",
          "The system figure counts a ticket as resolved when an answer was sent. Whether the customer's problem was actually solved is not observable here.", "",
          "## Technical performance", ""]
    lat = t["latency_ms"]
    L += [f"- Latency, triage only (classify + search + route): p50 {fmt(lat['triage_p50'], ' ms')}, p95 {fmt(lat['triage_p95'], ' ms')}",
          f"- Latency, end to end (including answer drafting): p50 {fmt(lat['total_p50'], ' ms')}, p95 {fmt(lat['total_p95'], ' ms')} "
          f"({t['cached_generations']} drafts came from cache)"]
    if "intent_accuracy" in t:
        c = t["calibration"]
        L += [f"- Intent: accuracy {fmt(t['intent_accuracy'], '%')}, macro precision {fmt(t['intent_macro_precision'], '%')}",
              f"- Urgency: accuracy {fmt(t['urgency_accuracy'], '%')}",
              f"- Calibration: mean stated intent confidence {fmt(c['mean_intent_confidence'], '%')} vs accuracy {fmt(c['intent_accuracy'], '%')} "
              f"(gap {fmt(c['gap_points'])} points; condition: within 5)",
              f"- Routing agreement with `expected_route`: {fmt(t['route_agreement'], '%')}  ({', '.join(f'{k}: {n}' for k, n in sorted(t['route_confusion'].items()))})",
              f"- Retrieval hit rate (an expected article among the passages kept): {fmt(t['retrieval_hit_rate'], '%')}",
              f"- Citations that point to a retrieved passage: {fmt(t['citations_within_retrieved'], '%')} of automated replies",
              f"- Automated replies citing an expected article: {fmt(t['auto_replies_citing_an_expected_doc'], '%')} "
              "(automatic proxy; whether each citation supports its sentence needs human review)", "",
              "| Intent | Precision | Recall | Tickets |", "|---|---|---|---|"]
        L += [f"| {k} | {fmt(x['precision'], '%')} | {fmt(x['recall'], '%')} | {x['n']} |" for k, x in t["intent_per_class"].items()]
        L += ["", "| Urgency | Precision | Recall | Tickets |", "|---|---|---|---|"]
        L += [f"| {k} | {fmt(x['precision'], '%')} | {fmt(x['recall'], '%')} | {x['n']} |" for k, x in t["urgency_per_class"].items()]
    else:
        L.append("- The input has no labels, so accuracy, routing agreement and retrieval hit rate cannot be computed.")
    L += ["", "## Safety", ""]
    if m["safety"]:
        s = m["safety"]
        L.append(f"- Automated replies sent to protected (`must_not_auto_respond`) tickets: **{s['auto_responses_on_protected_tickets']}** "
                 f"of {s['protected_tickets']} protected tickets (target 0)")
    else:
        L.append("- No labels, so protected tickets cannot be counted.")
    L += ["", "## Governance", "",
          "| Stage | Decisions logged | Decisions expected |", "|---|---|---|"]
    L += [f"| {k} | {g['decisions_logged'][k]} | {g['decisions_expected'][k]} |" for k in g["decisions_expected"]]
    L += ["", f"- Log reconciles with tickets processed: **{'yes' if g['reconciles'] else 'NO'}**",
          f"- Guardrail activations by check: {g['guardrail_activations'] or 'none'}",
          f"- Drafts containing private data (blocked): {g['pii_detections']}",
          f"- Automated replies carrying the automation disclosure: {fmt(g['auto_replies_with_disclosure'], '%')}",
          f"- Escalations with a complete context packet: {fmt(g['escalations_with_complete_packet'], '%')}", "",
          "## Fairness", "",
          f"A gap of more than {FAIRNESS_GAP_POINTS:.0f} points between groups is flagged. Small groups make gaps noisy, so check the ticket counts."]
    for name, block in m["fairness"].items():
        L += ["", f"### By {name}", "", "| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |", "|---|---|---|---|---|---|"]
        L += [f"| {grp} | {x['n']} | {fmt(x['auto_rate'], '%')} | {fmt(x['route_agreement'], '%')} | {fmt(x['retrieval_hit_rate'], '%')} | {fmt(x['guardrail_block_rate'], '%')} |"
              for grp, x in block["groups"].items()]
        flags = [f"{k.replace('_', ' ')} ({x['gap_points']} points)" for k, x in block["gaps"].items() if x["flag"]]
        L += ["", "Gaps over the limit: " + (", ".join(flags) if flags else "none")]
    L += ["", "## Answer quality against expert reference answers", ""]
    q = m["answer_quality"]
    if q:
        L += [f"- Automated replies that have a reference answer: {q['replies_with_reference']}",
              f"- Required points covered (`must_mention`): {fmt(q['must_mention_coverage'], '%')} across {q['replies_with_must_mention']} replies that have required points",
              f"- Forbidden claims found (`must_not_claim`, exact phrase match): {q['must_not_claim_violations']}"]
    else:
        L.append("- No reference answers are available for these tickets (the pack provides them for development tickets only).")
    L += ["", "## What this report does not measure", "",
          "- Hallucination rate and sentence-level citation accuracy need a human-reviewed sample (at least 50 replies, two reviewers).",
          "- Customer satisfaction and repeat contacts cannot be observed without live customers.", ""]
    return "\n".join(L)
