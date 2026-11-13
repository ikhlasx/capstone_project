# AI-use declaration: draft for the student to complete

> **Draft.** This lists what the AI coding assistant knows it produced in this project. Ikhlas PV
> must check every row, add any other AI tools used, and put the final version in the report. The
> course rule: "Anything you did not write yourself must be attributed, including code produced by
> an AI tool."

## Why this matters for this repository

The commits in this repository were originally marked with `Co-Authored-By: Claude` lines. On
12 November 2026 the history was rewritten and those lines were removed, so `git log` no longer
shows which work was AI-assisted. This declaration is therefore the record assessors will rely on.
Commits made after that date carry the line again.

## Tool 1: Claude Code (Anthropic), used as a coding assistant

Models used across sessions: Claude Opus, Sonnet, Haiku and Fable (Anthropic). Used from
8 to 13 November 2026.

| Area | What the assistant did | What the student did |
|---|---|---|
| `requirements.txt`, `docs/setup-notes.md` | Chose and pinned dependencies, verified them in a clean environment, documented the changes from the course pack | — *(student to complete)* |
| `src/` (all modules) | Wrote the code: ingest, models, config, chunking, retrieval, classifier, routing, generation, guardrails, decision log, pipeline, API, metrics, kill switch | — |
| `prompts/` | Drafted prompt PR-01 and the prompt register | — |
| `tests/` | Wrote all tests (230), including the failure-injection tests | — |
| `scripts/` | Wrote build, training, smoke-test, demo and kill-switch scripts | — |
| `evaluation/` | Wrote the harness, metrics, both threshold sweeps and the human-review kit; ran the sweeps and the validation and development runs | — |
| `.github/workflows/ci.yml` | Wrote the CI configuration | — |
| `README.md`, `docs/architecture.md`, `docs/failure-handling.md`, `docs/governance.md`, `docs/video-guide.md`, `docs/report-outline.md` | Drafted these documents | — |
| `docs/PRD.md` | Drafted version 1 from the student's discovery evidence, at the student's request | Reviewed and edited *(student to describe)* |
| Design decisions inside the code | Made and documented: calibration method, billing-dispute rule, incident rule left off, relevance and confidence thresholds (from development-data sweeps), kill-switch design | Accepted or changed *(student to confirm each)* |
| `discovery/problem_statement.md` | Fact-checked figures and quotes against the data and transcripts; applied one wording fix at the student's request ("take longest to resolve"); arranged the student's supplied text in the file | Wrote the statement *(student to confirm, see Tool 2)* |
| Video script | Fact-checked the draft script and listed corrections (`docs/video-guide.md`) | — |

The assistant did not write: the evaluation interpretation, the reflection, or the human review
verdicts.

## Tool 2: other AI tools *(student to complete)*

Text from at least one other AI tool was pasted into this project during the work. The student
must name the tool(s) and say what each produced. Items the assistant saw arrive in that form:

| Item | Student to state |
|---|---|
| Earlier drafts of the problem statement, including the six-element table, the one-paragraph version for Marcus, and the transcript-check table | Tool name, and which parts remain in the final version |
| `discovery/analysis.py` change adding table E11, and the matching `evidence.md` update | Who or what made it |
| The filled-in stage workbooks in `workbooks/`, added by a "workbook population script" | Tool name, and which sections were AI-written |
| The Stage 5 reflection answers | Who wrote them. The course requires the reflection to be your own |
| The first draft of the video script | Tool name |

## Statement *(student to write)*

A short paragraph in your own words: which tools you used, for what, how you checked their output,
and which parts are entirely your own.
