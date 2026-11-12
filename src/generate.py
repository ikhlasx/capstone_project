"""Answer drafting with a language model (FR-06). Used only after routing has decided to answer.

- The prompt lives in `prompts/build/PR-01_generate.md` and is versioned. The version is logged
  with every generation decision.
- The provider is called through a small interface so tests and CI can use a stub with no key.
- Responses are cached in SQLite by (model, prompt version, messages), so re-running the harness
  does not repeat calls.
- Rate limits, timeouts and server errors are retried with exponential backoff. Anything that
  still fails raises `GenerationFailed`, and the pipeline escalates the ticket (A11).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict

from .models import Ticket
from .retrieve import Passage

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "build" / "PR-01_generate.md"
MAX_TICKET_CHARS = 4000


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompt_id: str
    version: str
    system: str
    user_template: str

    @property
    def label(self) -> str:
        return f"{self.prompt_id}@{self.version}"


def load_prompt(path: Path = PROMPT_PATH) -> Prompt:
    text = path.read_text(encoding="utf-8")
    version = re.search(r"\*\*Version:\*\*\s*([\w.]+)", text)
    system = re.search(r"^## System\s*\n(.*?)^## User\s*\n", text, re.S | re.M)
    user = re.search(r"^## User\s*\n(.*)\Z", text, re.S | re.M)
    if not (version and system and user):
        raise ValueError(f"{path}: expected '**Version:**', '## System' and '## User' sections")
    return Prompt(prompt_id=path.stem.split("_")[0], version=version.group(1),
                  system=system.group(1).strip(), user_template=user.group(1).strip())


class Draft(BaseModel):
    model_config = ConfigDict(frozen=True)

    can_answer: bool
    answer: str
    citations: tuple[str, ...]
    unsure_about: str
    model: str
    prompt_version: str
    cached: bool = False
    attempts: int = 1


class GenerationFailed(Exception):
    """The model could not produce a usable draft. `reason` is a short machine-readable code."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# --- providers -----------------------------------------------------------------------------

class Provider(Protocol):
    name: str

    def complete(self, messages: list[dict[str, str]], model: str) -> str: ...


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, base_url: str, timeout: float = 30.0):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)

    def complete(self, messages: list[dict[str, str]], model: str) -> str:
        resp = self._client.chat.completions.create(
            model=model, messages=messages, temperature=0, max_tokens=500)
        return resp.choices[0].message.content or ""


class StubProvider:
    """Deterministic stand-in for tests and CI: answers from the first passage it is given."""

    name = "stub"

    def complete(self, messages: list[dict[str, str]], model: str) -> str:
        ids = re.findall(r"^\[([^\]\s]+)\]", messages[-1]["content"], re.M)
        if not ids:
            return json.dumps({"can_answer": False, "answer": "", "citations": [], "unsure_about": "no passages"})
        return json.dumps({"can_answer": True,
                           "answer": f"The documentation covers this. Please follow the steps in the cited article [{ids[0]}].",
                           "citations": [ids[0]], "unsure_about": ""})


def is_retryable(exc: Exception) -> bool:
    """Rate limits, timeouts, connection drops and 5xx responses are worth retrying."""
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status in (408, 409, 429) or status >= 500
    name = type(exc).__name__
    return any(k in name for k in ("Timeout", "Connection", "RateLimit", "InternalServer", "APIError")) \
        or isinstance(exc, (TimeoutError, ConnectionError))


# --- cache ---------------------------------------------------------------------------------

class LLMCache:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, response TEXT NOT NULL)")
        self._conn.commit()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(model: str, prompt_label: str, messages: list[dict[str, str]]) -> str:
        blob = json.dumps([model, prompt_label, messages], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT response FROM cache WHERE key = ?", (key,)).fetchone()
        if row:
            self.hits += 1
            return row[0]
        self.misses += 1
        return None

    def put(self, key: str, response: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO cache (key, response) VALUES (?, ?)", (key, response))
        self._conn.commit()


# --- prompt assembly and parsing -----------------------------------------------------------

def sanitise_ticket_text(text: str) -> str:
    """Stop a ticket from closing its own delimiter, and cap its length."""
    text = re.sub(r"(?i)</?\s*(ticket|passages)\s*>", " ", text)
    return text[:MAX_TICKET_CHARS]


def build_messages(prompt: Prompt, ticket: Ticket, passages: Sequence[Passage]) -> list[dict[str, str]]:
    blocks = "\n\n".join(f"[{p.chunk_id}] {p.title} — {p.section}\n{p.text}" for p in passages)
    user = (prompt.user_template
            .replace("{passages}", blocks)
            .replace("{subject}", sanitise_ticket_text(ticket.subject) or "(none)")
            .replace("{body}", sanitise_ticket_text(ticket.body)))
    return [{"role": "system", "content": prompt.system}, {"role": "user", "content": user}]


def parse_draft(raw: str) -> dict:
    """Pull the JSON object out of the model's reply. Raises ValueError if it is not usable."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        raise ValueError("no JSON object in the response")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("response JSON is not an object")
    can = data.get("can_answer")
    if isinstance(can, str):
        can = can.strip().lower() == "true"
    answer = data.get("answer") or ""
    cites = data.get("citations") or []
    if not isinstance(can, bool) or not isinstance(answer, str) or not isinstance(cites, list):
        raise ValueError("response JSON has the wrong field types")
    return {"can_answer": can, "answer": answer.strip(),
            "citations": tuple(str(c).strip().strip("[]") for c in cites if str(c).strip()),
            "unsure_about": str(data.get("unsure_about") or "").strip()}


# --- the generator -------------------------------------------------------------------------

class Generator:
    def __init__(self, provider: Provider, model: str, cache: LLMCache | None = None,
                 prompt: Prompt | None = None, max_attempts: int = 3, backoff_seconds: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.provider = provider
        self.model = model
        self.cache = cache
        self.prompt = prompt or load_prompt()
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    def generate(self, ticket: Ticket, passages: Sequence[Passage]) -> Draft:
        if not passages:
            raise GenerationFailed("no_passages")
        messages = build_messages(self.prompt, ticket, passages)
        # The provider name is part of the key so stub answers never get served as real ones.
        key = LLMCache.key(f"{self.provider.name}:{self.model}", self.prompt.label, messages)

        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return Draft(**parse_draft(hit), model=self.model, prompt_version=self.prompt.label, cached=True)

        last = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                raw = self.provider.complete(messages, self.model)
                fields = parse_draft(raw)
            except (ValueError, json.JSONDecodeError) as exc:
                last = f"invalid_json: {exc}"            # malformed output: worth one more try
            except Exception as exc:
                if not is_retryable(exc):
                    raise GenerationFailed("provider_error", type(exc).__name__) from exc
                last = f"provider_unavailable: {type(exc).__name__}"
            else:
                if self.cache is not None:
                    self.cache.put(key, raw)
                return Draft(**fields, model=self.model, prompt_version=self.prompt.label, attempts=attempt)
            if attempt < self.max_attempts:
                self._sleep(self.backoff_seconds * 2 ** (attempt - 1))

        reason, _, detail = last.partition(": ")
        raise GenerationFailed(reason, detail)
