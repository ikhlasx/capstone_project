# Governance: risk, fairness, decision logging and incident response

Follows the course Governance Framework section by section. Every control named here is a piece
of code or a procedure that exists in this repository, with the file that implements it.

> **Draft for Ikhlas PV to review.** The likelihood and impact ratings, the owners and the
> declaration in section 6 are positions the student must agree with and be able to defend.

## 1. Decision logging

Every automated decision is written to SQLite (`src/logging_store.py`), one row per stage per
ticket, with every field of the Governance Framework minimum record: `decision_id`, `timestamp`,
`ticket_id`, `stage`, `input_summary` (private data masked), `model` name and version, `prediction`
and confidence, `alternatives`, `sources_used` with scores, `threshold_applied`, `action_taken`,
`reason`, `guardrail_results`, `prompt_version` and `requirement_ids` (FR/NFR ids from the PRD).
Rows are only ever inserted, never updated.

**Coverage check.** Each harness run counts logged decisions against tickets processed, per stage,
and reports whether they reconcile. Both evaluation runs reconcile exactly:

| Run | Classification | Routing | Generation | Validation | Reconciles |
|---|---|---|---|---|---|
| Validation (80 tickets) | 80 / 80 | 80 / 80 | 64 / 64 | 64 / 64 | yes |
| Development (500 tickets) | 500 / 500 | 500 / 500 | 400 / 400 | 400 / 400 | yes |

If a ticket crashes the pipeline itself, the harness still escalates it, but the report then shows
that the log does **not** reconcile, so the gap is visible rather than silent
(`tests/test_failure_injection.py::test_unexpected_internal_error_is_caught_per_ticket`).

To read the decisions for one ticket: `python -m scripts.demo log <TICKET_ID>`.

## 2. Risk register

Likelihood and impact on a 1–5 scale. Owner for all risks: Ikhlas PV (system owner). In a real
deployment, R-02 and R-03 would also name CloudServe's security lead, and R-05 the technical writer.

| ID | Risk | Likelihood | Impact | Mitigation in this design | Evidence | Owner |
|---|---|---|---|---|---|---|
| R-01 | The system answers confidently and incorrectly | 3 | 5 | Answers are drafted only from retrieved passages (prompt PR-01, temperature 0). The grounding guardrail blocks any citation that was not retrieved, and a draft with no citation. Low intent confidence (< 0.80) and no relevant passage (< 0.40) escalate. The model can decline (`can_answer: false`), which blocks. Every reply says it is automated and names its source, so the customer can check. | 7 blocks on development, 2 on validation. Human review kit in `evaluation/human_review/` measures the remaining hallucination rate. | Ikhlas PV |
| R-02 | Private data appears in an outbound response | 2 | 5 | The PII guardrail blocks emails, phone numbers, card numbers (Luhn-checked) and secrets in every draft. The prompt forbids personal data. Ticket text is masked in log summaries and escalation packets. | 0 PII detections in 580 tickets. 5 PII tests plus a failure-injection test. | Ikhlas PV |
| R-03 | A customer's input is treated as an instruction | 3 | 4 | Ticket text sits inside `<ticket>` delimiters and the prompt declares it data. Delimiter tags inside a ticket are stripped. The injection guardrail blocks a draft when the ticket contains instruction-like text or the reply talks about its instructions. Routing is rule-based, so a ticket cannot talk its way into an automated reply. | 3 injection tests and 1 end-to-end attack test: none auto-answered. | Ikhlas PV |
| R-04 | Some customer groups receive worse answers | 4 | 3 | Every run reports outcomes split by tier, region, fluency, ticket length and channel, and flags gaps over 5 points (section 3). Retrieval embeds the ticket's meaning rather than matching keywords, which is the main fix for non-fluent wording. | Retrieval gap for non-fluent tickets of 7.4 points on development, which remains open. | Ikhlas PV |
| R-05 | The documentation the system relies on goes stale | 3 | 4 | Answers come only from the 29 reviewed articles, never from agents' personal answer files. Every reply cites its article, so a wrong answer can be traced to the article (Ines's requirement). The index is rebuilt from `data/documentation.json` with one command. | Not monitored automatically. Next step: alert on articles past their review date (`last_reviewed_days_ago`). | Ikhlas PV (with the technical writer) |
| R-06 | The model provider becomes unavailable | 3 | 3 | Only drafting uses the network. Timeouts, 429s and 5xx responses are retried with exponential backoff, then the ticket escalates with its packet. Classification, retrieval, routing and logging are local and keep working. The response cache serves repeats. | 25 failure-injection tests, plus live runs with no key and with a rejected key (`docs/failure-handling.md`). | Ikhlas PV |
| R-07 | Latency degrades under load | 3 | 2 | Triage is local (p95 57 ms on validation). Drafting is the slow part (end-to-end p95 11 s, which misses the 3 s target). The API processes tickets one at a time behind a lock, so heavy load queues requests. Prometheus histograms (`triage_latency_seconds`, `triage_total_latency_seconds`) make degradation visible. | Load not tested beyond sequential runs. | Ikhlas PV |
| R-08 | Costs rise unexpectedly with volume | 2 | 2 | Only answerable tickets call the model (about 80% of volume, one call each, max 500 output tokens). Escalations cost nothing. Responses are cached. CI never calls the model (stub provider). | Not metered per ticket. Next step: log token usage. | Ikhlas PV |
| R-09 | Wrong routing because the training labels are inconsistent | 4 | 3 | Found during the build: identical tickets carry different labels (186 tickets in 67 groups disagree on urgency, 36 groups on "answerable"). Urgency is therefore used only to order the queue, never to decide an automated reply. Protected intents, which the classifier predicts at 100% accuracy on validation, are what keep risky tickets away from automation. | `evaluation/results/classifier_sweep_dev.md`, section 5. | Ikhlas PV |

## 3. Fairness audit

**Method.** Each harness run splits every ticket's outcome by customer tier, region, language
fluency, ticket length (at or under / over the development median of 28 words) and channel. For
each segment it reports the automated-answer rate, agreement with the labelled correct route, the
retrieval hit rate (an expected article among the passages kept), and the guardrail block rate. A
gap of more than 5 points between segments is flagged. The validation set has 80 tickets and the
development set 500, so the development figures are the steadier of the two. Development figures
use a classifier trained on the same tickets, so routing results there are optimistic.

**Quality score.** No human-rated quality score exists yet. Routing agreement and retrieval hit
rate are used as proxies until the human review (`evaluation/human_review/`) is complete.

| Segment | Dev tickets | Dev auto-answered | Dev routing agreement | Dev retrieval hit | Val tickets | Val routing agreement | Val retrieval hit |
|---|---|---|---|---|---|---|---|
| Enterprise customers | 83 | 84.3% | 77.1% | 94.9% | 8 | 87.5% | 100.0% |
| Business customers | 164 | 75.6% | 81.7% | 90.2% | 30 | 73.3% | 100.0% |
| Standard customers | 253 | 78.7% | 77.5% | 94.3% | 42 | 73.8% | 92.0% |
| Fluent English | 380 | 79.7% | 78.4% | **94.8%** | 61 | **82.0%** | 95.5% |
| Non-fluent English | 120 | 75.0% | 80.0% | **87.4%** | 19 | **52.6%** | 100.0% |
| Short tickets (≤ 28 words) | 273 | 74.0% | 81.7% | 90.7% | 46 | 76.1% | 96.3% |
| Long tickets (> 28 words) | 227 | 84.1% | 75.3% | 95.7% | 34 | 73.5% | 96.2% |
| Chat (no subject line) | 155 | 81.3% | 80.0% | **89.9%** | 22 | 81.8% | **84.6%** |
| Forum | 55 | 78.2% | 76.4% | **97.3%** | 11 | 72.7% | 100.0% |
| Latin America | 60 | 86.7% | 78.3% | 95.3% | 7 | 85.7% | 100.0% |

**Gaps over 5 points, and what is known about each:**

1. **Retrieval for non-fluent tickets: 7.4 points lower on development (87.4% vs 94.8%).** This is the gap the Governance Framework predicts. It shows on the larger set but not on validation (19 non-fluent tickets), so it should be treated as real. It matters because a missed article means either an escalation (slower) or an answer from a less relevant passage, which the guardrails do not catch.
2. **Routing agreement for non-fluent tickets on validation: 52.6% vs 82.0% (29.4 points).** The 19-ticket group is small, and on development the gap disappears (80.0% vs 78.4%). It is reported, but it is most likely noise from the label inconsistency described in R-09.
3. **Chat tickets retrieve worse** (89.9% development, 84.6% validation, against 97.3% for forum). Chat tickets have no subject line, so the search has less text to work with.
4. **Auto-answer rate varies by tier on validation** (66.7% standard, 90.0% business), but by less on development (75.6%–84.3%). An automated answer is not by itself better or worse service. The question to watch is Ravi's point that a widening gap between plans "will come up at renewal".
5. **Latin America**, which had the lowest historical satisfaction (2.73, discovery E6), gets the highest automated-answer rate on development (86.7%). Whether that improves its experience depends on answer quality, which the human review must check.

## 4. Guardrails

All six run on every drafted answer (`src/guardrails.py`). Any failure blocks the draft. The
ticket is escalated with the blocked draft and the failed checks attached, and the validation row
in the log records each check's result.

| Guardrail | What it checks | When it fires |
|---|---|---|
| Private data (`pii`) | Emails, phone numbers, Luhn-valid card numbers, API keys, tokens and passwords in the reply | Block and escalate. Never redact and send. |
| Grounding (`grounding`) | Every citation is a passage that was retrieved for this ticket, and there is at least one | Block and escalate, listing the unsupported citation |
| Instruction integrity (`injection`) | The ticket does not contain instructions aimed at the system, and the reply does not talk about its own instructions | Block and escalate. The input is kept in the packet for review. |
| Commitments (`forbidden_claims`) | No refund or credit promised, no "fixed on our side", no fix dates or timelines | Block and escalate |
| Tone and scope (`tone`) | Reply length 40–2,500 characters, not mostly capitals | Block and escalate |
| Confidence floor (`confidence`) | The model said the passages answer the ticket. The routing confidence threshold was applied before any draft existed. | Block and escalate |

Observed: 2 blocks on validation and 7 on development. In every case the model declined
(`confidence`) and returned an empty draft, which also failed `grounding` and `tone`. To see each
guardrail block a real draft: `python -m scripts.demo guardrail`.

## 5. Incident response

For someone unfamiliar with the system, at two in the morning.

| Step | What to do | Who | How long |
|---|---|---|---|
| 1. Detect | An incident is a wrong, harmful or leaked automated reply, or a sudden change in behaviour. Signals: a customer or agent report; `/metrics` showing a jump in `triage_guardrail_blocks_total`, `triage_pii_detections_total` or `triage_generation_failures_total`; `/health` reporting `degraded`. | On-call support lead | Minutes after the signal |
| 2. Contain | **Turn on the kill switch:** `python -m scripts.kill_switch on "short reason"`, or create the file `storage/KILL_SWITCH` by hand. From the next ticket on, nothing is auto-answered. Check with `python -m scripts.kill_switch status`, and confirm on `/metrics` that new tickets are counted under `rule="kill_switch"`. | On-call support lead | Under 1 minute |
| 3. Assess | Find the affected replies: the decision log (`storage/decisions.db`) has every decision with its ticket id, prompt version, sources and guardrail results. Use `python -m scripts.demo log <TICKET_ID>` for one ticket. Decide whether the cause is the article (send to the technical writer), the retrieval or routing (system owner), or the model (system owner). | System owner | Within 4 hours |
| 4. Notify | Tell the head of support (Marcus) what happened, how many customers received an affected reply, and that automation is off. If private data was exposed, follow CloudServe's data-breach procedure and involve the security lead. Affected customers get a corrected reply from a person. | Head of support | Same working day |
| 5. Remediate | Fix the cause: correct the article and rebuild the index (`python -m scripts.build_index`), add a guardrail pattern or routing rule, or change the prompt version. Add a test that reproduces the incident. Run the full validation set (`python -m evaluation.harness …`) and check safety and reconciliation before turning the kill switch off. | System owner | Depends on the cause |
| 6. Review | Within a week, write up what happened, why the controls did not stop it, and what changed. Record the change in the PRD revision log, and the new test in the risk register evidence. | System owner and head of support | Within 1 week |

### The kill switch

| Question | Answer |
|---|---|
| What is the mechanism? | A file, `storage/KILL_SWITCH` (path configurable with `KILL_SWITCH_FILE`). While it exists, every ticket that would have been answered is escalated with its packet instead (rule `kill_switch`). Classification, search, escalation and logging continue. Code: `src/pipeline.py`; command: `scripts/kill_switch.py`. |
| Who is authorised to use it? | The head of support, the on-call support lead and the system owner. Anyone who can write files on the deployment can operate it, by design, so it works even if the tooling does not. |
| How long until it takes effect? | From the next ticket processed. The file is checked on every ticket, with no restart or deployment. |
| What happens to tickets in flight? | A ticket already past routing finishes normally: it can still receive its automated reply. Every later ticket is escalated. |
| How is it tested? | `tests/test_pipeline_harness.py::test_kill_switch_stops_auto_answers_without_a_restart` switches it on and off mid-run and checks the decision log. Before relying on it, run `python -m scripts.kill_switch on test`, send one ticket, check it escalates with `kill_switch`, then turn it off. |

## 6. The declaration

| Statement | Position |
|---|---|
| This system must never … | send an automated reply to a security, compliance, feature or unclear ticket; promise a refund, credit or fix date; include private data in a reply; or state anything that is not in a retrieved help article. |
| The mechanism that enforces that is … | Deterministic routing rules that escalate protected intents before any draft exists (0 of 101 protected tickets auto-answered across both sets), and six guardrails that run on every draft and block on any failure. Both are rule-based code with tests, not model behaviour. |
| The most likely way it could still cause harm is … | A fluent, well-cited reply that misreads the article or answers a slightly different question. The citation is real, so grounding passes, but the advice is wrong. The guardrails cannot see this. Only human review can measure it. |
| We would not deploy this without first … | completing the two-person human review and getting the hallucination rate under 5%; running in shadow mode on live tickets, with an agent approving every reply, for at least two weeks; closing or explaining the non-fluent retrieval gap; and agreeing the kill-switch owners with CloudServe. |
