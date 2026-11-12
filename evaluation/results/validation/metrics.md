# Metrics report: validation

- Input: `data/validation_tickets.json` (80 tickets processed, 0 unreadable records)
- Run: `0f785d3859aa` at 2026-11-12T04:17:19+00:00 · provider: openrouter · model: `meta-llama/llama-3.1-8b-instruct`
- Thresholds: intent confidence 0.8, retrieval relevance 0.4
- **These are validation figures.** Thresholds were set on development data only.

## Volume

| Processed | Auto-answered | Escalated | of which blocked by guardrails | of which drafting failed |
|---|---|---|---|---|
| 80 | 62 | 18 | 2 | 0 |

Reason each ticket ended where it did: `answerable` 62, `protected_intent` 14, `no_relevant_passage` 2, `guardrail_block` 2

## Business outcomes

| Measure | This system | What humans did on the same tickets (history) |
|---|---|---|
| First-contact resolution (auto-answered ÷ all) | 77.5% | 46.2% |
| Escalation rate | 22.5% | 53.8% |
| Response time | median 0.88 s, mean 2.98 s (system processing time) | median 218.0 min (time to resolve) |

The system figure counts a ticket as resolved when an answer was sent. Whether the customer's problem was actually solved is not observable here.

## Technical performance

- Latency, triage only (classify + search + route): p50 45.7 ms, p95 57.2 ms
- Latency, end to end (including answer drafting): p50 884.3 ms, p95 10954.2 ms (6 drafts came from cache)
- Intent: accuracy 100.0%, macro precision 100.0%
- Urgency: accuracy 43.8%
- Calibration: mean stated intent confidence 97.9% vs accuracy 100.0% (gap 2.1 points; condition: within 5)
- Routing agreement with `expected_route`: 75.0%  (expected auto_respond -> got auto_respond: 45, expected auto_respond -> got escalate: 3, expected escalate -> got auto_respond: 17, expected escalate -> got escalate: 15)
- Retrieval hit rate (an expected article among the passages kept): 96.2%
- Citations that point to a retrieved passage: 100.0% of automated replies
- Automated replies citing an expected article: 97.8% (automatic proxy; whether each citation supports its sentence needs human review)

| Intent | Precision | Recall | Tickets |
|---|---|---|---|
| account_access | 100.0% | 100.0% | 4 |
| api_key_issue | 100.0% | 100.0% | 6 |
| api_usage_question | 100.0% | 100.0% | 4 |
| authentication_failure | 100.0% | 100.0% | 3 |
| billing_query | 100.0% | 100.0% | 10 |
| compliance_request | 100.0% | 100.0% | 1 |
| configuration_help | 100.0% | 100.0% | 3 |
| data_export | 100.0% | 100.0% | 1 |
| data_residency | 100.0% | 100.0% | 6 |
| database_issue | 100.0% | 100.0% | 1 |
| deployment_failure | 100.0% | 100.0% | 5 |
| feature_request | 100.0% | 100.0% | 3 |
| integration_help | 100.0% | 100.0% | 3 |
| onboarding | 100.0% | 100.0% | 4 |
| performance_degradation | 100.0% | 100.0% | 3 |
| quota_or_overage | 100.0% | 100.0% | 2 |
| rate_limit | 100.0% | 100.0% | 1 |
| rollback_request | 100.0% | 100.0% | 6 |
| security_incident | 100.0% | 100.0% | 4 |
| sso_configuration | 100.0% | 100.0% | 1 |
| unclear_request | 100.0% | 100.0% | 6 |
| webhook_issue | 100.0% | 100.0% | 3 |

| Urgency | Precision | Recall | Tickets |
|---|---|---|---|
| high | 42.9% | 24.0% | 25 |
| low | 50.0% | 5.0% | 20 |
| medium | 43.8% | 80.0% | 35 |

## Safety

- Automated replies sent to protected (`must_not_auto_respond`) tickets: **0** of 14 protected tickets (target 0)

## Governance

| Stage | Decisions logged | Decisions expected |
|---|---|---|
| classification | 80 | 80 |
| routing | 80 | 80 |
| generation | 64 | 64 |
| validation | 64 | 64 |

- Log reconciles with tickets processed: **yes**
- Guardrail activations by check: {'grounding': 2, 'tone': 2, 'confidence': 2}
- Drafts containing private data (blocked): 0
- Automated replies carrying the automation disclosure: 100.0%
- Escalations with a complete context packet: 100.0%

## Fairness

A gap of more than 5 points between groups is flagged. Small groups make gaps noisy, so check the ticket counts.

### By tier

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| business | 30 | 90.0% | 73.3% | 100.0% | 3.3% |
| enterprise | 8 | 87.5% | 87.5% | 100.0% | 0.0% |
| standard | 42 | 66.7% | 73.8% | 92.0% | 2.4% |

Gaps over the limit: auto rate (23.3 points), route agreement (14.2 points), retrieval hit rate (8.0 points)

### By region

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| asia_pacific | 21 | 81.0% | 81.0% | 100.0% | 4.8% |
| europe | 25 | 80.0% | 76.0% | 94.7% | 4.0% |
| latin_america | 7 | 57.1% | 85.7% | 100.0% | 0.0% |
| north_america | 27 | 77.8% | 66.7% | 92.9% | 0.0% |

Gaps over the limit: auto rate (23.9 points), route agreement (19.0 points), retrieval hit rate (7.1 points)

### By fluency

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| fluent | 61 | 77.0% | 82.0% | 95.5% | 1.6% |
| non_fluent | 19 | 78.9% | 52.6% | 100.0% | 5.3% |

Gaps over the limit: route agreement (29.4 points)

## Answer quality against expert reference answers

- No reference answers are available for these tickets (the pack provides them for development tickets only).

## What this report does not measure

- Hallucination rate and sentence-level citation accuracy need a human-reviewed sample (at least 50 replies, two reviewers).
- Customer satisfaction and repeat contacts cannot be observed without live customers.
