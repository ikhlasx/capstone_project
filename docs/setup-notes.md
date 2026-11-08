# Setup notes (build step 1)

## Interpreter

Python **3.11** (verified on 3.11.7, Windows x64). 3.11 was chosen over 3.12 for the widest
wheel coverage across torch / chromadb / sentence-transformers.

```bash
py -3.11 -m venv .venv          # Windows; elsewhere: python3.11 -m venv .venv
.venv/Scripts/activate          # Windows; elsewhere: source .venv/bin/activate
pip install -r requirements.txt
```

## Dependency changes from the course pack

| Change | Reason |
|---|---|
| Removed `langchain`, `langchain-openai` | Pack pinned `langchain-openai 0.0.7` with `openai 1.0.0`, which conflict. The design calls the LLM directly; no orchestration framework is needed. |
| `openai` pinned to the current release | Used only as an OpenAI-compatible client pointed at OpenRouter (`src/config.py: OPENROUTER_BASE_URL`). |
| `torch` / `transformers` pinned explicitly | They arrive transitively through `sentence-transformers`; pinning stops silent upgrades from changing embeddings between runs. |

Only top-level packages are pinned. Transitive dependencies resolve from these pins.

## Verification (2026-11-08)

1. A fresh, empty Python 3.11 venv was created outside the repo.
2. `pip install --no-cache-dir -r requirements.txt` was run in it, so nothing came from the dev venv or the pip cache.
3. `pip check` reported "No broken requirements found."
4. Every top-level package imported cleanly (`torch 2.15.0+cpu`, `chromadb 1.5.9`, `openai 3.46.0`, `pydantic 2.14.3`).

## Live model call

```bash
cp .env.example .env            # then put your OpenRouter key in .env
python -m scripts.smoke_llm
```

Exit code 0 means the call succeeded. 2 means no key is configured, and 1 means the call
failed. The script never prints the key.
