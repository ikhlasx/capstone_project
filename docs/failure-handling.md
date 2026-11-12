# Failure handling (acceptance criterion A11)

The rule is the same for every failure: **the run continues, and the affected ticket is escalated
to a person with its context packet.** No failure produces an automated reply, and no failure
stops the batch.

## What was injected, and what happened

Each row is a full harness run with one failure injected. The automated tests are in
`tests/test_failure_injection.py` (25 tests). They use stand-in components so they run without an
API key. Run them with `python -m pytest tests/test_failure_injection.py -v`.

| Failure | How the system responds | Ticket outcome | Test |
|---|---|---|---|
| No API key configured | No provider is created. Classification, search and routing still run locally. | Escalated: `generation_failed:no_api_key` | `test_no_api_key_escalates_everything_answerable` |
| Invalid API key (401) | Not retried, because retrying cannot help. | Escalated: `generation_failed:provider_error` | `test_invalid_key_401_fails_fast_without_retries` |
| Provider timeout | Retried 3 times with backoff (2 s, 4 s), then given up. | Escalated: `generation_failed:provider_unavailable` | `test_provider_timeout_on_every_call` |
| Rate limit (429), temporary | Retried with backoff until it succeeds. | Answered normally | `test_rate_limit_429_is_retried_and_recovers` |
| Rate limit (429), permanent | Retried 3 times, then given up. | Escalated | `test_permanent_rate_limit_escalates` |
| Server error (5xx) | Retried 3 times, then given up. | Escalated | `test_server_error_500_is_retried_then_escalated` |
| Outage that starts mid-run | Tickets before the outage are answered. Tickets after it are escalated. | Mixed | `test_outage_that_starts_mid_run` |
| Garbage model output (empty, prose, broken JSON, HTML error page, wrong types) | Retried, never cached, then given up. | Escalated: `generation_failed:invalid_json` | `test_garbage_model_output_escalates` |
| Model cites a passage that does not exist | The grounding guardrail blocks the draft. | Escalated: `guardrail_block` | `test_invented_citations_are_blocked_by_the_guardrail` |
| Model output contains private data or a refund promise | The PII and forbidden-claims guardrails block the draft. | Escalated: `guardrail_block` | `test_model_output_with_private_data_or_promises_is_blocked` |
| Document index missing | Search fails and no answer can be grounded. | Escalated: `retrieval_unavailable` | `test_missing_document_index` |
| No matching documentation (nonsense text, emoji only) | Nothing clears the thresholds. | Escalated | `test_tickets_with_no_matching_documentation` |
| Empty, null or whitespace-only ticket body | Detected at ingest and flagged. | Escalated: `empty_ticket` | `test_malformed_input_records` |
| Records that are not tickets (strings, numbers, null, lists) | Skipped and counted as unreadable records in the report. | Not processed; counted | `test_malformed_input_records` |
| Missing id, unknown channel, wrong field types, bad date, 90,000-character body, mixed scripts and null bytes, duplicate ids | Repaired at ingest, each repair recorded in `ingest_warnings`. | Processed normally | `test_malformed_input_records` |
| Empty ticket file | An empty report is written. | — | `test_empty_ticket_file_produces_an_empty_report` |
| Unreadable ticket file (invalid JSON, wrong shape, missing) | A one-line message and exit code 2. No stack trace. | — | `test_unreadable_ticket_file_exits_with_a_message` |
| Ticket that tries to give the system instructions | The ticket text cannot close its delimiter, and the injection guardrail blocks any draft. | Escalated | `test_tickets_that_try_to_instruct_the_system_are_never_auto_answered` |
| Unexpected crash inside the pipeline | Caught per ticket by the harness. The report shows the log no longer reconciles, so the gap is visible. | Escalated: `internal_error` | `test_unexpected_internal_error_is_caught_per_ticket` |

## Checked against the real system (12 November 2026)

Two failures were also injected into the real configuration (real embedding model, real index,
real classifier, live provider), on the first 20 validation tickets:

| Injected | Result |
|---|---|
| `OPENROUTER_API_KEY` empty | 20 processed, 0 auto-answered, 13 escalated as `generation_failed:no_api_key`, 7 as protected. Log reconciles. Exit code 0. |
| An invalid key, rejected by OpenRouter with a real 401 | 20 processed, 0 auto-answered, 13 escalated as `generation_failed:provider_error`, 7 as protected. Log reconciles. Exit code 0. |

In both runs every escalated ticket still carried its five retrieved passages in the context
packet, so the person picking it up has the relevant articles even though no answer was drafted.

## Known limits

- A provider that returns a well-formed but wrong answer is not a "failure" these tests can see.
  That is what the grounding guardrail and the human review sample are for.
- Retries make a failing ticket slow: three attempts with 2 s and 4 s waits, plus up to 30 s per
  attempt for a timeout. A long outage therefore slows the run but does not stop it.
- If the decision log itself cannot be written (for example, the disk is full), the ticket is
  still escalated by the harness, but the report will show that the log does not reconcile.
