"""Session-wide fixtures: a classifier and a document index built with the fake embedder."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.chunking import chunk_corpus, load_corpus
from src.classify import TicketClassifier
from src.ingest import load_tickets
from src.retrieve import Retriever
from tests.helpers import FakeEmbedder

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="session")
def dev_set():
    return load_tickets(DATA / "development_tickets.json").tickets


@pytest.fixture(scope="session")
def fake_classifier(dev_set):
    return TicketClassifier(FakeEmbedder()).fit(dev_set)


@pytest.fixture(scope="session")
def fake_retriever(tmp_path_factory):
    r = Retriever(FakeEmbedder(), tmp_path_factory.mktemp("session-index") / "chroma")
    r.build(chunk_corpus(load_corpus(DATA / "documentation.json")))
    return r
