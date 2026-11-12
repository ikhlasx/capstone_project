# Prompt register

Every prompt the system uses lives in this folder and is versioned. The version is logged with
each generation decision (`prompt_version` in the decision log), so any answer can be traced to
the exact prompt text that produced it. When a prompt's text changes, raise its version and add
a line to its change history here.

| ID | File | Category | Version | Serves | Model | Change history |
|---|---|---|---|---|---|---|
| PR-01 | `build/PR-01_generate.md` | Build | 1.0 | FR-06, FR-07, FR-10 | `MODEL_NAME` (default `meta-llama/llama-3.1-8b-instruct`) | 1.0: first version |

## How PR-01 defends against instructions hidden in tickets

1. The ticket is wrapped in `<ticket>` tags, and the system text says its content is data, never instructions.
2. Any `<ticket>` or `<passages>` tags inside the ticket are stripped before it is inserted, so a ticket cannot close its own delimiter (`src/generate.py: sanitise_ticket_text`).
3. The output is checked by rules that do not depend on the model (`src/guardrails.py`): a ticket that contains instruction-like text is blocked and escalated, and so is a reply that cites anything not retrieved or makes a forbidden claim.

## Folders

- `build/`: prompts that run inside the system.
- `evaluation/`: prompts used to judge answers during evaluation (none yet).
