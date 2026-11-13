# CloudServe Support Triage

A ticket triage and grounded-answer system for CloudServe support. It reads each incoming ticket,
answers the ones the existing help articles already cover (with citations), and sends the rest to
a person with a context packet, ordered by urgency. It is not a chatbot.

FDE Capstone, IIT Roorkee. Author: Ikhlas PV. AI assistance is declared in the report.

## Run it from a clean checkout

Requires Python 3.11.

```bash
git clone https://github.com/ikhlasx/capstone_project capstone
cd capstone
python -m venv .venv
```

Activate the environment (Windows: `.venv\Scripts\activate`, macOS/Linux: `source .venv/bin/activate`), then:

```bash
pip install -r requirements.txt
cp .env.example .env
```

Put your OpenRouter key in `.env` as `OPENROUTER_API_KEY`. Never commit `.env`.

Run the tests (no API key needed):

```bash
python -m pytest tests/ -v
```

Process a ticket file end to end:

```bash
python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/validation
```

The first run downloads the embedding model, builds the document index and trains the classifier
(about a minute). `--input` can be any path to a ticket file. Add `--provider stub` to run without
an API key.

## What the harness writes

| File | Contents |
|---|---|
| `metrics.md`, `metrics.json` | Volume, business, technical, safety, governance, fairness and answer-quality figures |
| `results.jsonl` | One line per ticket: the action, the reason, and the reply or escalation packet |
| `escalation_queue.json` | Escalated tickets ordered by urgency, then age |
| `decisions.db` | The decision log for the run (SQLite, one row per stage per ticket) |

## Run it as a service

```bash
uvicorn src.api:app --port 8000
```

| Endpoint | What it does |
|---|---|
| `GET /health` | Whether the index is loaded and a model provider is configured |
| `POST /tickets` | Process one ticket (any channel's fields) and return the reply or the escalation packet |
| `GET /metrics` | Prometheus metrics: tickets by action and rule, guardrail blocks, drafting failures, latency |

```bash
curl -X POST localhost:8000/tickets -H "Content-Type: application/json"   -d '{"ticket_id": "T-1", "channel": "chat", "body": "my deployment keeps dying at the health check stage"}'
```

## Continuous integration

`.github/workflows/ci.yml` runs on every push: it installs the pinned requirements, runs the full
test suite, and processes the validation set end to end with the stub provider. It uses no API
key, and it fails if any protected ticket is auto-answered or the decision log does not reconcile.

## How a ticket moves through the system

```
ingest     any channel -> one Ticket record                       src/ingest.py
classify   intent (22) + urgency (3) + confidence, local model    src/classify.py
retrieve   top passages from the 29 help articles, with scores    src/retrieve.py
route      fixed rules and thresholds, no language model          src/route.py
generate   draft an answer from the passages only, with citations src/generate.py
validate   guardrails that can block the draft                    src/guardrails.py
act        send the reply with a disclosure, or escalate          src/pipeline.py
log        one decision row per stage                             src/logging_store.py
```

A ticket is escalated when it is empty, when its intent is protected (security, compliance,
feature request, unclear), when the classifier is not confident, when it disputes a charge, when
no passage is relevant enough, when drafting fails, or when a guardrail blocks the draft.

## Stopping automated replies (kill switch)

```bash
python -m scripts.kill_switch on "reason"     # nothing is auto-answered from the next ticket
python -m scripts.kill_switch status
python -m scripts.kill_switch off
```

Tickets are still classified, searched, escalated and logged while the switch is on. See
`docs/governance.md` for the incident procedure.

## Human review of answers

```bash
python -m evaluation.human_review.make_review_sheets --results evaluation/results/validation/results.jsonl --tickets data/validation_tickets.json
python -m evaluation.human_review.score_review --a evaluation/human_review/reviewer_A.csv --b evaluation/human_review/reviewer_B.csv
```

Two reviewers fill in their sheets independently, following `evaluation/human_review/RUBRIC.md`.

## Other commands

```bash
python -m scripts.build_index                # rebuild the document index
python -m scripts.train_classifier           # retrain the classifier
python -m scripts.smoke_llm                  # one live model call
python -m evaluation.retrieval_sweep --input data/development_tickets.json
python -m evaluation.threshold_sweep --input data/development_tickets.json
python discovery/analysis.py --data data --out discovery/evidence.md
python -m scripts.demo ticket "my deployment keeps dying"   # readable walkthrough of one ticket
```

The two sweeps run on development data only and refuse any other set.

## Repository layout

```
src/          the pipeline
prompts/      versioned prompts and the prompt register
evaluation/   harness, metrics, threshold sweeps, results
discovery/    evidence analysis and problem statement
docs/         PRD, architecture, governance, failure handling, report outline
tests/        python -m pytest tests/ -v
data/         course datasets
storage/      runtime files (index, model, cache, logs); never committed
```
