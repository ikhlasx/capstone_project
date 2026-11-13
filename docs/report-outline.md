# Report outline

The report is a single PDF of 20–30 pages, excluding appendices, in the Submission Guide's section
order. It must be continuous prose with numbered, captioned figures and tables, and every
performance claim needs to say how it was measured and on what data. File name:
`IkhlasPV_Capstone_Report.pdf` (use your enrolled name).

This outline tells you what each section needs and where the evidence is. **It does not write the
report.** Sections or parts marked ✍️ are where the course assesses your own judgement (problem
framing, evaluation interpretation, reflection), and must be written by you. The facts and figures
for every section are in the files listed.

| # | Section | Pages | Evidence to use |
|---|---|---|---|
| 1 | Executive summary | 1 | Write last. One paragraph each: problem, what you built, what it achieved (77.5% answered without escalation on validation, 0 of 14 protected tickets auto-answered), and the single most important caveat. ✍️ Choosing the caveat is your judgement. |
| 2 | The problem | 2–3 | ✍️ `discovery/problem_statement.md` (your statement), the interview transcripts. |
| 3 | Discovery findings | 3–4 | `discovery/evidence.md` (E1, E2, E7, E8, E11), transcripts. Present findings in prose, and put the tables in Appendix A. |
| 4 | Requirements | 2–3 | `docs/PRD.md`: FR-01–FR-16 and NFR-01–NFR-08, each traced to evidence. The "How the requirements map to the build" table. |
| 5 | Architecture and design | 3–4 | `docs/architecture.md` (diagram, routing rules, the alternatives table, thresholds and their source). |
| 6 | Implementation | 2–3 | Git history, `docs/setup-notes.md`, `docs/failure-handling.md`. The difficult parts are below. |
| 7 | Evaluation | 3–4 | `evaluation/results/validation/metrics.md`, `development/metrics.md`, both sweep reports, the human review results. ✍️ The interpretation is yours. |
| 8 | Governance and risk | 2–3 | `docs/governance.md` (decision logging, risk register, fairness audit, guardrails, incident procedure, kill switch, declaration). |
| 9 | The requirements revision | 1–2 | Stage 5 revision log, PRD section 7. ✍️ What it taught you is yours. |
| 10 | Conclusions | 1–2 | ✍️ What you would do next, and what remains uncertain. |
| — | Appendices | unlimited | See the list at the end. |

## What each section needs

### 3. Discovery findings
The findings that changed the design, each with its evidence:
- 71% of tickets are answerable from the 29 articles (E1), and 49% of all escalations were answerable ones (138 of 281).
- Answerable tickets resolved at first contact: median 32 min, CSAT 3.41, 0% repeat contacts. Answerable but escalated: 717 min, 2.56, 42% (E11). These are different tickets, so this does not prove escalation caused the gap.
- High-urgency tickets take longest to resolve: median 342 min vs 132 for low (E7), because the queue is worked oldest first (Sofia).
- All 87 `must_not_auto_respond` labels sit in four intents (E8).
- Interviews: keyword search fails (Ines's example), escalations arrive without context (Daniel), "rather it said nothing than said something wrong" (Marcus), customers want to know a reply is automated (Ravi).
- Stakeholders are sometimes wrong. Marcus says FCR is 42%, but the data says 44%. Sofia says non-fluent customers have the worst satisfaction, but the data shows 3.04 against 2.95 for fluent customers (E5). The workbook expects you to notice this kind of thing.

### 6. Implementation: what was difficult
- **Calibration.** The standard sigmoid calibration reported 69% confidence on predictions that were 99.8% right (30.5-point gap). It was replaced by plain multinomial logistic regression with C=64 (2.6-point gap).
- **Label noise.** 254 development tickets fall into 97 groups with identical text. 67 of those groups (186 tickets) disagree on urgency, 36 on "answerable", and 30 on the expected route. This caps achievable routing agreement near 80% and urgency accuracy near 50%.
- **The relevance threshold** could not separate tickets that have no article: only 14.7% came back empty at 0.40.
- **Billing disputes.** The obvious keyword rule matched 0 of 500 tickets, and the phrase the data does label for escalation is labelled auto-respond in 6 of its 8 copies.
- **Thread safety** in the API (SQLite connections shared across worker threads) and model start-up time counted in the first ticket's latency. Both were found and fixed.
- What you would restructure (✍️).

### 7. Evaluation
**Method.** Thresholds were chosen on development data only (out-of-fold for the classifier).
Validation was then run once, unattended, with no changes afterwards. The development run gives the
answer-quality figures, because reference answers exist only for development tickets. The human
review covers what automatic metrics cannot.

**Results to report** (lead with business, then technical, then governance, as the guide asks):

| Measure | Validation (80) | Development (500) |
|---|---|---|
| Answered without escalation | 77.5% (humans: 46.2%) | 78.6% (humans: 43.8%) |
| Escalation rate | 22.5% (humans: 53.8%) | 21.4% (humans: 56.2%) |
| Protected tickets auto-answered | 0 of 14 | 0 of 87 |
| Routing agreement with labels | 75.0% | 78.8% |
| Intent accuracy | 100% | 100% (trained on these tickets) |
| Urgency accuracy | 43.8% | 58.6% (trained on these tickets); out-of-fold 52.2% |
| Calibration gap | 2.1 points | 1.5 points; out-of-fold 2.6 |
| Retrieval hit rate | 96.2% | 93.0% |
| Citations pointing to retrieved passages | 100% | 100% |
| `must_mention` coverage | — | 43.9% (57 replies) |
| `must_not_claim` violations | — | 0 |
| Triage latency p50 / p95 | 45.7 / 57.2 ms | 44.3 / 59.0 ms |
| End-to-end p95 | 11.0 s (misses the 3 s target) | 9.3 s |
| Hallucination rate, citation accuracy | from the human review | — |

**Limits to state plainly.** Validation is only 80 tickets. "Answered without escalation" is not
the same as resolved, and satisfaction is not observable. System seconds and human resolution
minutes measure different things. Development figures are optimistic because the classifier
trained on those tickets. The end-to-end latency target is missed.

✍️ **Interpretation.** What these numbers mean for Marcus, what they do not prove, and why routing
agreement is 75% (the 17 tickets labelled "escalate" that were answered).

### 9. The requirements revision
The changes from version 1, which must match your Stage 5 log exactly:
1. Assumption A1 (a relevance threshold can detect tickets with no article) was false, so routing now relies on intent rules for those.
2. Urgency cannot be read reliably from text (label noise), so it orders the queue and never decides an automated reply. The incident rule was left off.
3. Calibration method changed (30.5 → 2.6 points).
4. FR-12 billing disputes narrowed to explicit disputes, with the forbidden-claims guardrail as the backstop.
5. Kill switch added after the governance review found none existed (new control, NFR-02).
6. Fairness audit extended to ticket length and channel. It found chat tickets retrieve worse, because they have no subject line.

## Figures and tables to include (number them in order)

| Suggested figure or table | Source |
|---|---|
| Fig. 1: pipeline diagram | `docs/architecture.md` (the Mermaid diagram renders on GitHub, so screenshot it) |
| Table 1: discovery evidence (E1, E2, E7, E11) | `discovery/evidence.md` |
| Table 2: requirements traceability | `docs/PRD.md` |
| Table 3: routing rules in order | `docs/architecture.md` |
| Table 4: design alternatives considered | `docs/architecture.md` |
| Fig. 2: retrieval threshold sweep (hit rate and correct-empty against threshold) | `evaluation/results/retrieval_sweep_dev.md` |
| Table 5: calibration, before and after | `evaluation/results/classifier_sweep_dev.md` |
| Table 6: headline results, validation and development | section 7 above |
| Table 7: fairness audit | `docs/governance.md` section 3 |
| Table 8: risk register | `docs/governance.md` section 2 |
| Table 9: failure-injection results | `docs/failure-handling.md` |
| Table 10: human review results | `evaluation/human_review/review_results.md` |

## Appendices
- A. Full discovery evidence tables (`discovery/evidence.md`).
- B. The five completed stage workbooks.
- C. Prompt register and full text of PR-01 (`prompts/`).
- D. Full metrics reports for validation and development.
- E. Both sweep reports.
- F. Per-class precision and recall (from `metrics.md`).
- G. Human review rubric and results.
- H. AI-use declaration (final version of `docs/ai-use-declaration-draft.md`).
- I. Key code listings: routing rules (`src/route.py`), guardrails (`src/guardrails.py`).
