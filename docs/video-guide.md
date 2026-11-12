# Video guide

What to show in each section of the video, the exact commands, and the checked numbers. Every
figure below was read from the committed result files on 12 November 2026. If you re-run
anything before recording, read the new numbers off the screen rather than this page.

## Before you record

1. Open a terminal in `E:\iit roorke\capstone`, activate the environment (`.venv\Scripts\activate`), and set the font to 16 or larger.
2. **Warm up once:** run the three demo commands in section 4 below one time before recording. The first run loads the models and calls the live model, which can take 10–25 seconds per answer. On camera, the repeat is fast because the answer comes from the cache, and the output says so (`answer from cache`). Say that plainly.
3. Open these files in the editor, one tab each:
   `discovery/evidence.md`, `README.md`, `evaluation/results/validation/metrics.md`, `docs/failure-handling.md`, `docs/PRD.md`.

## Section by section

| Section | Show this | File or command |
|---|---|---|
| 1. The problem | Webcam only | — |
| 2. Discovery | Tables E1, E2, E7, E11 | `discovery/evidence.md` (E11 is at the bottom) |
| 2. Discovery | Problem statement | `discovery/problem_statement.md` |
| 3. Architecture | The seven-step diagram | `README.md`, section "How a ticket moves through the system" |
| 3. Architecture | The routing rules in order | `src/route.py`, the docstring at the top |
| 4.1 Tests | Full test run | `python -m pytest tests/ -v` (228 tests, about 25–30 s) |
| 4.2 Grounded answer | One ticket, step by step | `python -m scripts.demo ticket "my deployment keeps dying at the container health check phase"` |
| 4.3 Escalation | Protected ticket and its packet | `python -m scripts.demo ticket "Our auditor requires access logs covering the last six months for our annual compliance review." --subject "Audit documentation request" --channel email --id DEMO-02` |
| 4.4 Guardrails | Real checks blocking bad drafts | `python -m scripts.demo guardrail` |
| 4.4 Guardrails (optional) | The guardrail tests | `python -m pytest tests/test_generate_guardrails.py -v` |
| 4.5 Full run | The unattended harness | `python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/demo_run` |
| 4.5 Audit log | Decision rows for one ticket | `python -m scripts.demo log DEMO-01` |
| 4.5 API (optional) | Health and metrics | `uvicorn src.api:app --port 8000`, then open `localhost:8000/health` and `localhost:8000/metrics` |
| 5. Numbers | The report | `evaluation/results/validation/metrics.md` |
| 6. Fairness | Fairness tables | the "Fairness" section of the same file |
| 6. Failure testing | The failure table | `docs/failure-handling.md` |
| 6. CI (optional) | Green CI run | https://github.com/ikhlasx/capstone_project/actions |
| 7. What I got wrong | Assumptions and revisions | `docs/PRD.md` section 7, and your Stage 5 revision log |

The 4.5 harness run makes a live model call for each answerable ticket not already in the
cache. If it was run before, most answers come from the cache and it finishes in about a minute.
A cold run takes several minutes, so if you are short of time, start it and cut to the result.

## What each demo shows (checked runs)

| Demo | What happened |
|---|---|
| DEMO-01, deployment | `deployment_failure`, confidence 0.95. Top passages DOC-DEPLOY-001 (scores 0.82, 0.81, 0.78). Rule `answerable`. All six checks passed. The reply carries the disclosure and names DOC-DEPLOY-001. **Time: 23 s cold (live model and model loading), 0.05 s from cache.** |
| DEMO-02, audit logs | `compliance_request`, confidence 0.99. Rule `protected_intent`, escalated. No model call. The packet attaches DOC-SEC-003 (symptoms and resolution) and DOC-SEC-001. |
| DEMO-03, "ignore all previous instructions… refund…" | Classified `unclear_request` (confidence 0.51), so **routing escalated it before any draft was written. The guardrails never ran on this ticket.** |
| `scripts.demo guardrail` | Four drafts, all blocked: refund promise and "fixed on our side" (forbidden_claims), an email address (pii), a citation to an article that wasn't retrieved (grounding), a fix date (forbidden_claims). A clean draft passes. |

## Checked numbers

**Validation set (80 tickets, one unattended run, live model)**

| Figure | Value |
|---|---|
| Auto-answered / escalated | 62 (77.5%) / 18 (22.5%) |
| Humans on the same tickets (history) | 46.2% first-contact resolution, 53.8% escalated, median 218 min to resolve |
| Protected tickets auto-answered | 0 of 14 |
| Escalation reasons | protected 14, no relevant passage 2, guardrail block 2 |
| Guardrail activations | grounding 2, tone 2, confidence 2 (the same 2 drafts failed 3 checks each) |
| Intent accuracy | 100% (80 tickets; 0 errors) |
| Urgency accuracy | 43.8% |
| Calibration gap | 2.1 points (stated 97.9% vs actual 100%) |
| **Routing agreement with `expected_route`** | **75.0%**: 17 tickets labelled "escalate" were auto-answered, 3 labelled "auto-respond" were escalated |
| Right article among passages kept | 96.2% |
| Citations pointing to retrieved passages | 100% |
| Triage latency | p50 45.7 ms, p95 57.2 ms |
| **End-to-end latency** | **median 0.88 s, mean 2.98 s, p95 11.0 s**: misses the 3 s target |
| Decision log | 80 / 80 / 64 / 64 per stage, reconciles |

**Fairness on validation** (5-point limit, flagged gaps):
- **Fluency:** routing agreement 82.0% fluent vs **52.6% non-fluent (29.4-point gap)**. Retrieval: 95.5% vs 100%.
- **Tier:** auto-answered 66.7% standard vs 90.0% business (23.3 points). Retrieval 92.0% vs 100% (8.0 points).
- **Region:** auto-answered 57.1% Latin America (7 tickets) vs 81.0% Asia-Pacific.

**Development set (500 tickets, full run with reference answers)**

| Figure | Value |
|---|---|
| Auto-answered | 78.6% (humans: 43.8%) |
| Protected auto-answered | 0 of 87 |
| Routing agreement | 78.8% (94 labelled "escalate" were auto-answered) |
| Urgency accuracy | 58.6% (training data, so optimistic) |
| Required points covered (`must_mention`) | 43.9% across 57 replies |
| Forbidden claims (exact phrase) | 0 |
| Guardrail blocks | 7 |

**Development sweeps (out-of-fold, so fair estimates)**
- Retrieval at threshold 0.40: right article in top 5 for 93.0% (94.8% fluent vs 87.4% non-fluent, a 7.4-point gap). Only 14.7% of tickets with no article came back empty.
- Intent: 99.8% accuracy. Urgency: 52.2% (most-common-level baseline: 45.2%).
- First calibration method (sigmoid on top of logistic regression): stated 69.3% vs actual 99.8%, a **30.5-point gap**. After switching to plain multinomial logistic regression with C=64: 97.2% vs 99.8%, a **2.6-point gap**.
- 254 tickets fall into 97 groups with identical subject and body. In 67 of those groups (186 tickets) the urgency labels disagree. 36 groups disagree on "answerable", 30 on the expected route.

**Other**
- Tests: 228 passing. Failure-injection: 25 tests. CI: green on GitHub.
- Chunks: 116. Thresholds: confidence 0.80, relevance 0.40.

## Corrections to the video script

Change these before recording. Each one is either wrong or would be caught by an assessor.

1. **4.2: "resolved in under 900 milliseconds"** is not true for a live answer. The cold run took 23 s. Say: "This answer came from the cache because I ran it once before recording. A live answer takes several seconds, mostly the language model writing it."
2. **4.2: "near 100% confidence"**: it is 0.95. Read the number off the screen.
3. **4.4: DEMO-03 does not show a guardrail block.** Routing escalated it as `unclear_request` before any draft existed. Run DEMO-03, say "routing caught this first, so no draft was ever written", then run `python -m scripts.demo guardrail` to show the guardrails blocking four real bad drafts. Delete the paragraph that says "input sanitization stripped hostile delimiter tags… the classification and routing logic flagged the adversarial nature": routing escalated it because the classifier wasn't sure what it was, not because it detected an attack.
4. **4.5: the `sqlite3` query** has no run filter, so after several demo runs it prints duplicate rows. Use `python -m scripts.demo log DEMO-01` instead.
5. **5: routing agreement is missing.** The strongest honest point in your results is that 17 of 80 tickets the labels say should be escalated were auto-answered (75.0% agreement), and why: identical tickets carry different labels, which caps agreement near 80%. Leaving it out while quoting 77.5% would look like hiding it.
6. **5: "the system replied in under a second"**: that is the median. The 95th percentile is 11 s, which misses the brief's 3 s target. Say both.
7. **5: urgency accuracy** on validation is 43.8%. If you mention urgency, use that figure, and note that the escalation queue is ordered by this prediction.
8. **6: "On validation that gap was gone"** is true only for retrieval. The flagged gaps on validation are larger elsewhere: routing agreement 82.0% fluent vs 52.6% non-fluent, and auto-answer rate 66.7% standard tier vs 90.0% business. Say those, and that the groups are small.
9. **7: "Switching to multinomial logistic regression closed it"**: it was already multinomial logistic regression. What changed is that the sigmoid calibration layer was removed and the regularisation was loosened (C=64). Say: "I removed the calibration layer and retuned the model, which closed the gap from 30.5 points to 2.6."
10. **7: the relevance example "score above 0.50"** (also in your Stage 5 workbook): the measured finding is at threshold 0.40, where only 14.7% of no-article tickets come back empty.
11. **1: "he had run out of ways to explain it"** is not in the transcript. Marcus says he has reported a red number for two quarters. Cut the rest.
12. **Script checklist note C** lists "99.5% availability" as removed. Correct, keep it out.

The two sentences marked "YOUR OWN SENTENCE" (sections 5 and 7) are the evaluation interpretation and the reflection. The course assesses your judgement there, so write those yourself.
