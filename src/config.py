"""Runtime configuration, read from environment variables (optionally via a local .env).

Nothing here has side effects beyond reading the environment, so importing it in tests is safe
without an API key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# .env is optional; real environment variables always win over it.
load_dotenv(PROJECT_ROOT / ".env", override=False)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None
    model_name: str
    embedding_model: str
    chroma_path: str
    database_url: str
    log_level: str
    confidence_threshold: float
    retrieval_top_k: int

    @property
    def has_api_key(self) -> bool:
        key = self.openrouter_api_key
        return bool(key) and key != "your_key_here"


def get_settings() -> Settings:
    return Settings(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        model_name=os.getenv("MODEL_NAME", "meta-llama/llama-3.1-8b-instruct"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        chroma_path=os.getenv("CHROMA_PATH", "./storage/chroma"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./storage/decisions.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        confidence_threshold=_float("CONFIDENCE_THRESHOLD", 0.80),
        retrieval_top_k=_int("RETRIEVAL_TOP_K", 5),
    )
