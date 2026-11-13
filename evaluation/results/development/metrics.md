# Metrics report: development

- Input: `data/development_tickets.json` (500 tickets processed, 0 unreadable records)
- Run: `35b1acb4898b` at 2026-11-13T05:28:17+00:00 · provider: openrouter · model: `meta-llama/llama-3.1-8b-instruct`
- Thresholds: intent confidence 0.8, retrieval relevance 0.4
- **These are development figures.** Thresholds were set on development data only.

## Volume

| Processed | Auto-answered | Escalated | of which blocked by guardrails | of which drafting failed |
|---|---|---|---|---|
| 500 | 393 | 107 | 7 | 0 |

Reason each ticket ended where it did: `answerable` 393, `protected_intent` 87, `no_relevant_passage` 13, `guardrail_block` 7

## Business outcomes

| Measure | This system | What humans did on the same tickets (history) |
|---|---|---|
| First-contact resolution (auto-answered ÷ all) | 78.6% | 43.8% |
| Escalation rate | 21.4% | 56.2% |
| Response time | median 0.06 s, mean 0.06 s (system processing time) | median 214.0 min (time to resolve) |

The system figure counts a ticket as resolved when an answer was sent. Whether the customer's problem was actually solved is not observable here.

## Technical performance

- Latency, triage only (classify + search + route): p50 44.7 ms, p95 53.4 ms
- Latency, end to end (including answer drafting): p50 62.0 ms, p95 76.5 ms (400 drafts came from cache)
- Intent: accuracy 100.0%, macro precision 100.0%
- Urgency: accuracy 58.6%
- Calibration: mean stated intent confidence 98.5% vs accuracy 100.0% (gap 1.5 points; condition: within 5)
- Routing agreement with `expected_route`: 78.8%  (expected auto_respond -> got auto_respond: 299, expected auto_respond -> got escalate: 12, expected escalate -> got auto_respond: 94, expected escalate -> got escalate: 95)
- Retrieval hit rate (an expected article among the passages kept): 93.0%
- Citations that point to a retrieved passage: 100.0% of automated replies
- Automated replies citing an expected article: 93.0% (automatic proxy; whether each citation supports its sentence needs human review)

| Intent | Precision | Recall | Tickets |
|---|---|---|---|
| account_access | 100.0% | 100.0% | 22 |
| api_key_issue | 100.0% | 100.0% | 18 |
| api_usage_question | 100.0% | 100.0% | 24 |
| authentication_failure | 100.0% | 100.0% | 20 |
| billing_query | 100.0% | 100.0% | 24 |
| compliance_request | 100.0% | 100.0% | 26 |
| configuration_help | 100.0% | 100.0% | 17 |
| data_export | 100.0% | 100.0% | 29 |
| data_residency | 100.0% | 100.0% | 29 |
| database_issue | 100.0% | 100.0% | 26 |
| deployment_failure | 100.0% | 100.0% | 27 |
| feature_request | 100.0% | 100.0% | 20 |
| integration_help | 100.0% | 100.0% | 21 |
| onboarding | 100.0% | 100.0% | 22 |
| performance_degradation | 100.0% | 100.0% | 23 |
| quota_or_overage | 100.0% | 100.0% | 23 |
| rate_limit | 100.0% | 100.0% | 13 |
| rollback_request | 100.0% | 100.0% | 28 |
| security_incident | 100.0% | 100.0% | 26 |
| sso_configuration | 100.0% | 100.0% | 26 |
| unclear_request | 100.0% | 100.0% | 15 |
| webhook_issue | 100.0% | 100.0% | 21 |

| Urgency | Precision | Recall | Tickets |
|---|---|---|---|
| high | 73.6% | 53.4% | 146 |
| low | 88.9% | 6.2% | 128 |
| medium | 53.8% | 91.6% | 226 |

## Safety

- Automated replies sent to protected (`must_not_auto_respond`) tickets: **0** of 87 protected tickets (target 0)

## Governance

| Stage | Decisions logged | Decisions expected |
|---|---|---|
| classification | 500 | 500 |
| routing | 500 | 500 |
| generation | 400 | 400 |
| validation | 400 | 400 |

- Log reconciles with tickets processed: **yes**
- Guardrail activations by check: {'grounding': 7, 'tone': 7, 'confidence': 7}
- Drafts containing private data (blocked): 0
- Automated replies carrying the automation disclosure: 100.0%
- Escalations with a complete context packet: 100.0%

## Fairness

A gap of more than 5 points between groups is flagged. Small groups make gaps noisy, so check the ticket counts.

### By tier

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| business | 164 | 75.6% | 81.7% | 90.2% | 1.2% |
| enterprise | 83 | 84.3% | 77.1% | 94.9% | 0.0% |
| standard | 253 | 78.7% | 77.5% | 94.3% | 2.0% |

Gaps over the limit: auto rate (8.7 points)

### By region

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| asia_pacific | 119 | 73.9% | 76.5% | 92.1% | 0.8% |
| europe | 151 | 80.8% | 82.1% | 92.2% | 0.7% |
| latin_america | 60 | 86.7% | 78.3% | 95.3% | 1.7% |
| north_america | 170 | 77.1% | 77.6% | 93.5% | 2.4% |

Gaps over the limit: auto rate (12.8 points), route agreement (5.6 points)

### By fluency

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| fluent | 380 | 79.7% | 78.4% | 94.8% | 1.1% |
| non_fluent | 120 | 75.0% | 80.0% | 87.4% | 2.5% |

Gaps over the limit: retrieval hit rate (7.4 points)

### By length

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| long (> 28 words) | 227 | 84.1% | 75.3% | 95.7% | 0.9% |
| short (<= 28 words) | 273 | 74.0% | 81.7% | 90.7% | 1.8% |

Gaps over the limit: auto rate (10.1 points), route agreement (6.4 points)

### By channel

| Group | Tickets | Auto-answered | Routing agreement | Retrieval hit rate | Guardrail blocks |
|---|---|---|---|---|---|
| chat | 155 | 81.3% | 80.0% | 89.9% | 0.0% |
| docs_comment | 78 | 78.2% | 71.8% | 93.8% | 0.0% |
| email | 212 | 76.9% | 81.1% | 94.1% | 2.8% |
| forum | 55 | 78.2% | 76.4% | 97.3% | 1.8% |

Gaps over the limit: route agreement (9.3 points), retrieval hit rate (7.4 points)

## Answer quality against expert reference answers

- Automated replies that have a reference answer: 175
- Required points covered (`must_mention`): 43.9% across 57 replies that have required points
- Forbidden claims found (`must_not_claim`, exact phrase match): 0

## What this report does not measure

- Hallucination rate and sentence-level citation accuracy need a human-reviewed sample (at least 50 replies, two reviewers).
- Customer satisfaction and repeat contacts cannot be observed without live customers.
