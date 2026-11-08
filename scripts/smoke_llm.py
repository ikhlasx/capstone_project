"""One live model call through OpenRouter, to prove the key, model name and client work.

Usage:  python -m scripts.smoke_llm
Exit codes: 0 = live call succeeded, 2 = no API key configured, 1 = call failed.
The API key is never printed.
"""
from __future__ import annotations

import sys
import time

from openai import OpenAI

from src.config import OPENROUTER_BASE_URL, get_settings


def main() -> int:
    s = get_settings()
    if not s.has_api_key:
        print("No OPENROUTER_API_KEY set. Copy .env.example to .env and add your key.")
        return 2

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=s.openrouter_api_key, timeout=30)
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=s.model_name,
            messages=[{"role": "user", "content": "Reply with exactly the word: pong"}],
            max_tokens=5,
            temperature=0,
        )
    except Exception as exc:  # report the class only; messages can echo request details
        print(f"Live call FAILED: {type(exc).__name__}: {exc}")
        return 1

    elapsed = time.perf_counter() - started
    text = (resp.choices[0].message.content or "").strip()
    print(f"model={resp.model} latency={elapsed:.2f}s reply={text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
