# CloudServe Support Triage — Build Plan for Claude Code

FDE Capstone (IIT Roorkee). Individual project. Author: the student. Claude assists with code;
the student owns the problem statement, evaluation interpretation and reflection (course rule —
never draft those). All AI-generated code must be attributed in the report's AI-use declaration.

## What we are building (and not building)

NOT a chatbot. A ticket **triage and grounded-answer system**: it reads every incoming ticket,
answers the ones existing documentation already covers (with citations), and escalates the rest
to a human **with a context packet** (summary, likely intent, retrieved docs, what it was unsure
about), prioritised by urgency.

Evidence driving the design lives in `discovery/evidence.md` (regenerate with
`python discovery/analysis.py`). Key rows:
- E1: 71% of tickets answerable from the 29 docs; 49% of human escalations were answerable ones.
- E2: answerable tickets resolve in 48 min median vs 750 min for escalated non-answerable ones.
- E7: high-urgency tickets wait longest (342 min median) — queue is sorted by age, not urgency.
- E8: security_incident, compliance_request, feature_request, unclear_request carry all 87
  `must_not_auto_respond` labels; feature/unclear have no supporting docs.
- E6: region gap (Latin America CSAT 2.73 vs North America 3.05) — fairness audit must segment.

## Hard constraints (from the Build Specification — pass/fail)

| ID | Criterion | How this design meets it |
|---|---|---|
| A1 | Runs from clean checkout via README | Pinned + verified requirements; tested by cloning into an empty dir |
| A2 | 4 channels → one internal Ticket model | `src/ingest.py`, pydantic model, tolerant of empty/missing fields |
| A3 | Intent + urgency + numeric confidence | Local classifier (embeddings + calibrated logistic regression) |
| A4 | Retrieval returns real corpus passages | Chroma over section-aware chunks; ids `DOC-XXX-NNN#section` |
| A5 | Deterministic routing | Rules + threshold, no LLM in the routing decision |
| A6 | Citations resolve to retrieved passages | Generator may only cite ids passed to it; validator checks |
| A7 | Guardrail blocks | Validator runs on every response, blocks → escalate |
| A8 | Every decision logged, reconciles | SQLite, one row per stage per ticket, schema below |
| A9 | Full set unattended, arbitrary input path | `python -m evaluation.harness --input X --output Y`, per-ticket try/except |
| A10 | Metrics report auto-generated | `metrics.json` + `metrics.md` written by harness |
| A11 | Survives no-hit, timeout, outage, rate limit, bad input | Retry w/ backoff + cache; on LLM failure → escalate with packet, never crash |
| A12 | Tests via one command | `python -m pytest tests/ -v` |

## Architecture

```
ticket (any channel)
  └─ ingest      normalise → Ticket(id, channel, subject, body, tier, region, fluency, received_at)
  └─ classify    intent (22) + urgency (3), confidence, top-3 alternatives      [local, no LLM]
  └─ retrieve    top-k chunks from Chroma, relevance threshold → may return []  [local, no LLM]
  └─ route       deterministic rules:
                   1. intent in ALWAYS_ESCALATE (security_incident, compliance_request,
                      feature_request, unclear_request) → escalate
                   2. classifier confidence < CONFIDENCE_THRESHOLD → escalate
                   3. no retrieval hit above RELEVANCE_THRESHOLD → escalate
                   4. else → generate
  └─ generate    LLM (OpenRouter/Groq free tier) → JSON {answer, citations[], unsure_about}
                 ticket text wrapped in delimiters; system prompt says it is data, not instructions
  └─ validate    every response, can BLOCK (→ escalate):
                   pii · grounding (citations ⊆ retrieved ids) · forbidden claims (refunds,
                   "fixed on our side", delivery dates) · instruction integrity · confidence floor
  └─ action      auto_respond (with "drafted by an automated assistant" disclosure)
                 or escalate → EscalationPacket(summary, intent, urgency, docs, reason, unsure_about)
                    sorted by urgency, then age
  └─ log         decision row per stage (schema below) + Prometheus counters
```

Why the classifier is local, not an LLM: deterministic (A5), calibratable (governance
condition: stated confidence within 5 pts of accuracy), fast (p95 < 3 s), free, and it keeps
working when the provider is down (A11). The LLM is used only where language generation is
needed. Calibrate on development tickets; pick the threshold from a sweep, not by guessing.

Thresholds are set from data in `evaluation/threshold_sweep.py` and recorded in the PRD.

## Decision log schema (Governance Framework minimum record)

```json
{"decision_id","timestamp","ticket_id","stage":"classification|routing|generation|validation",
 "input_summary","model":{"name","version"},"prediction":{"value","confidence"},
 "alternatives":[{"value","confidence"}],"sources_used":[{"doc_id","score"}],
 "threshold_applied","action_taken":"auto_respond|escalate|block","reason",
 "guardrail_results":{"pii","grounding","tone","injection"},"prompt_version","requirement_ids":[]}
```
`requirement_ids` must reference real FR/NFR ids from the student's PRD.

## Repo layout

```
README.md  requirements.txt  .env.example  .gitignore (.env, storage/, .venv/)
src/ config.py models.py ingest.py classify.py retrieve.py route.py generate.py
     guardrails.py logging_store.py pipeline.py api.py metrics_server.py
prompts/build/PR-01_generate.md  prompts/evaluation/  prompts/README.md (register + versions)
evaluation/harness.py  evaluation/metrics.py  evaluation/threshold_sweep.py  evaluation/results/
discovery/analysis.py  discovery/evidence.md
tests/  docs/architecture.md  .github/workflows/ci.yml
data/  (pack datasets)   storage/ (runtime, never committed)
```

## Metrics report (harness must compute all of these)

- Volume: processed, auto-answered, escalated, blocked by guardrails
- Business: first-contact resolution, mean/median response time, escalation rate — shown next
  to the history baseline from the same tickets
- Technical: per-class precision/recall, routing accuracy vs `expected_route`, retrieval hit
  rate vs `expected_doc_ids`, citation accuracy, latency p50/p95
- Safety: count of auto-responses on `must_not_auto_respond` tickets (target 0)
- Governance: decisions logged vs tickets (must reconcile), guardrail activations by type,
  PII detections
- Fairness: the above split by tier, region, fluency (flag gaps > 5 pts)
- Answer quality (when ground truth exists): must_mention coverage, must_not_claim violations

## Build order (week-two checkpoints)

1. Setup: venv, own pinned requirements verified in a clean venv (the pack's list has version
   conflicts — e.g. langchain-openai 0.0.7 vs openai 1.0.0 — so verify and document changes),
   `.env.example`, `.gitignore`, one live model call.
2. Ingest + Ticket model + tests (one ticket per channel).
3. Retrieval: section-aware chunking, Chroma build script, relevance threshold, tests.
4. Classifier + calibration + threshold sweep; routing rules; SQLite log.
5. Generator with JSON output, caching, retry/backoff; guardrails that block.
6. Harness end-to-end on validation set, unattended. **This is the gate — do it early.**
7. Failure-injection tests (A11): no key, timeout, 429, empty body, garbage JSON.
8. FastAPI endpoint, Prometheus metrics, GitHub Actions CI (tests without an API key using
   a stub provider).
9. Clean-checkout rehearsal: clone to empty dir, follow README literally.

## Rules for Claude while working here

- Never commit or print API keys. `.env` is gitignored before it exists.
- No hardcoded dataset paths in the harness.
- Never tune against the hidden set; validation figures must be labelled as validation.
- Do not write the student's problem statement, evaluation interpretation, or reflection.
- Small commits with clear messages — commit history is assessed.
