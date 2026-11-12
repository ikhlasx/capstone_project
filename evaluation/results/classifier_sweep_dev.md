# Classifier and routing sweep (development)

Input: `data/development_tickets.json` · tickets: 500 · embedder: `all-MiniLM-L6-v2` · all predictions out-of-fold (5-fold). Development data only.

## 1. Classification

- Intent accuracy: **99.8%**, macro precision **99.8%**, macro recall **99.7%** (target: precision ≥ 85%)
- Urgency accuracy: **52.2%** (always guessing the most common level would score 45.2%)

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
| performance_degradation | 95.8% | 100.0% | 23 |
| quota_or_overage | 100.0% | 100.0% | 23 |
| rate_limit | 100.0% | 92.3% | 13 |
| rollback_request | 100.0% | 100.0% | 28 |
| security_incident | 100.0% | 100.0% | 26 |
| sso_configuration | 100.0% | 100.0% | 26 |
| unclear_request | 100.0% | 100.0% | 15 |
| webhook_issue | 100.0% | 100.0% | 21 |

| Urgency | Precision | Recall | Tickets |
|---|---|---|---|
| high | 64.5% | 41.1% | 146 |
| low | 38.5% | 3.9% | 128 |
| medium | 49.7% | 86.7% | 226 |

## 2. Calibration: intent

Mean stated confidence 97.2% vs accuracy 99.8% (gap **2.6 points**; condition: within 5). Expected calibration error: 2.8 points.

| Confidence band | Tickets | Mean confidence | Accuracy |
|---|---|---|---|
| 0.4-0.6 | 1 | 43.1% | 0.0% |
| 0.6-0.8 | 6 | 72.0% | 100.0% |
| 0.8-1.0 | 493 | 97.6% | 100.0% |

## 2. Calibration: urgency

Mean stated confidence 48.5% vs accuracy 52.2% (gap **3.7 points**; condition: within 5). Expected calibration error: 4.3 points.

| Confidence band | Tickets | Mean confidence | Accuracy |
|---|---|---|---|
| 0.2-0.4 | 30 | 38.8% | 43.3% |
| 0.4-0.6 | 461 | 48.9% | 52.9% |
| 0.6-0.8 | 9 | 63.3% | 44.4% |

## 3. Routing sweep over the intent-confidence threshold

Relevance threshold fixed at 0.4. "Agreement" is with the `expected_route` label.

### default (dispute + residency rules on, incident rule off)

| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | Auto but should escalate | Escalated but answerable |
|---|---|---|---|---|---|
| 0.30 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.35 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.40 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.45 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.50 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.55 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.60 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.65 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.70 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.75 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.80 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.85 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.90 | 78.0% | 77.0% | 0 | 97 | 18 |
| 0.95 | 71.0% | 72.4% | 0 | 91 | 47 |

### incident rule on

| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | Auto but should escalate | Escalated but answerable |
|---|---|---|---|---|---|
| 0.30 | 78.2% | 78.4% | 0 | 94 | 14 |
| 0.35 | 78.2% | 78.4% | 0 | 94 | 14 |
| 0.40 | 78.2% | 78.4% | 0 | 94 | 14 |
| 0.45 | 78.0% | 78.2% | 0 | 94 | 15 |
| 0.50 | 78.0% | 78.2% | 0 | 94 | 15 |
| 0.55 | 78.0% | 78.2% | 0 | 94 | 15 |
| 0.60 | 78.0% | 78.2% | 0 | 94 | 15 |
| 0.65 | 77.6% | 77.8% | 0 | 94 | 17 |
| 0.70 | 77.6% | 77.8% | 0 | 94 | 17 |
| 0.75 | 77.4% | 77.6% | 0 | 94 | 18 |
| 0.80 | 77.4% | 77.6% | 0 | 94 | 18 |
| 0.85 | 77.4% | 77.6% | 0 | 94 | 18 |
| 0.90 | 76.2% | 76.8% | 0 | 93 | 23 |
| 0.95 | 69.2% | 72.2% | 0 | 87 | 52 |

### dispute rule off

| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | Auto but should escalate | Escalated but answerable |
|---|---|---|---|---|---|
| 0.30 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.35 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.40 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.45 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.50 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.55 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.60 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.65 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.70 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.75 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.80 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.85 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.90 | 78.0% | 77.0% | 0 | 97 | 18 |
| 0.95 | 71.0% | 72.4% | 0 | 91 | 47 |

### residency rule off

| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | Auto but should escalate | Escalated but answerable |
|---|---|---|---|---|---|
| 0.30 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.35 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.40 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.45 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.50 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.55 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.60 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.65 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.70 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.75 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.80 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.85 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.90 | 78.0% | 77.0% | 0 | 97 | 18 |
| 0.95 | 71.0% | 72.4% | 0 | 91 | 47 |

### no protected-margin rule

| Confidence threshold | Auto-answered | Agreement | Protected tickets auto-answered | Auto but should escalate | Escalated but answerable |
|---|---|---|---|---|---|
| 0.30 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.35 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.40 | 80.0% | 78.6% | 0 | 98 | 9 |
| 0.45 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.50 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.55 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.60 | 79.8% | 78.4% | 0 | 98 | 10 |
| 0.65 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.70 | 79.4% | 78.0% | 0 | 98 | 12 |
| 0.75 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.80 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.85 | 79.2% | 77.8% | 0 | 98 | 13 |
| 0.90 | 78.0% | 77.0% | 0 | 97 | 18 |
| 0.95 | 71.0% | 72.4% | 0 | 91 | 47 |

Rules fired at confidence 0.8 (default variant): `{'answerable': 396, 'protected_intent': 87, 'no_relevant_passage': 11, 'low_confidence': 6}`

## 4. Billing-dispute rule on billing tickets

| Rule says dispute | Label says escalate | Tickets |
|---|---|---|
| no | no | 21 |
| no | yes | 3 |

## 5. Identical tickets with different labels

254 tickets fall into 97 groups that share the exact same subject and body.
Groups whose members disagree: intent 0, urgency 67, answerable 36, expected route 30.
No text-based system can predict a label that differs between identical tickets, so these counts cap achievable accuracy.

Reference point: routing every non-protected ticket to auto-answer using the *true* intent would agree with `expected_route` on **79.6%** of tickets.
