"""Tests for section-aware chunking and retrieval (A4).

Unit tests use a small deterministic bag-of-words embedder, so they are fast and need no
model download. One integration group uses the real sentence-transformers model and is
skipped if that model cannot be loaded (for example, offline CI).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.helpers import FakeEmbedder
from src.chunking import Chunk, chunk_corpus, chunk_document, load_corpus, slugify
from src.retrieve import (
    Passage,
    RetrievalUnavailable,
    Retriever,
    best_score_per_doc,
)

DATA = Path(__file__).resolve().parent.parent / "data"
CHUNK_ID = re.compile(r"^DOC-[A-Z]+-\d{3}#[a-z0-9-]+$")


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(DATA / "documentation.json")


@pytest.fixture(scope="module")
def chunks(corpus):
    return chunk_corpus(corpus)


@pytest.fixture
def retriever(tmp_path, chunks):
    r = Retriever(FakeEmbedder(), tmp_path / "chroma")
    r.build(chunks)
    return r


# --- chunking ------------------------------------------------------------------------------

def test_corpus_chunks_into_four_sections_per_doc(corpus, chunks):
    assert len(corpus) == 29
    assert len(chunks) == 116
    for doc in corpus:
        sections = [c.section for c in chunks if c.doc_id == doc["doc_id"]]
        assert sections == ["Symptoms", "Common causes", "Resolution", "Notes"]


def test_chunk_ids_are_unique_and_well_formed(chunks):
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert all(CHUNK_ID.match(i) for i in ids), [i for i in ids if not CHUNK_ID.match(i)]
    assert "DOC-DEPLOY-001#common-causes" in ids


def test_chunk_text_is_verbatim_corpus_text(corpus, chunks):
    by_id = {d["doc_id"]: d for d in corpus}
    for c in chunks:
        assert c.text and c.text in by_id[c.doc_id]["content"]
        assert not c.text.startswith("##")


def test_embed_text_carries_title_and_section(chunks):
    c = next(c for c in chunks if c.chunk_id == "DOC-DATA-003#resolution")
    assert c.title in c.embed_text and "Resolution" in c.embed_text and c.text in c.embed_text


def test_document_without_sections_is_one_chunk():
    [c] = chunk_document({"doc_id": "DOC-X-001", "title": "T", "content": "# T\n\nJust text."})
    assert c.chunk_id == "DOC-X-001#body" and "Just text." in c.text


def test_empty_document_gives_no_chunks():
    assert chunk_document({"doc_id": "DOC-X-002", "title": "T", "content": ""}) == []


def test_empty_sections_are_skipped_and_repeated_headings_disambiguated():
    doc = {"doc_id": "DOC-X-003", "title": "T",
           "content": "# T\n\n## Notes\n\n## Steps\n\nOne.\n\n## Steps\n\nTwo."}
    assert [c.chunk_id for c in chunk_document(doc)] == ["DOC-X-003#steps", "DOC-X-003#steps-2"]


def test_duplicate_chunk_ids_across_docs_are_rejected():
    doc = {"doc_id": "DOC-X-004", "title": "T", "content": "## A\n\nx"}
    with pytest.raises(ValueError, match="duplicate"):
        chunk_corpus([doc, doc])


@pytest.mark.parametrize("heading,slug", [("Common causes", "common-causes"),
                                          ("Resolution", "resolution"), ("  ??  ", "section")])
def test_slugify(heading, slug):
    assert slugify(heading) == slug


def test_load_corpus_rejects_non_list(tmp_path):
    p = tmp_path / "docs.json"
    p.write_text(json.dumps({"doc_id": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus(p)


# --- retrieval (fake embedder) -------------------------------------------------------------

def test_build_indexes_every_chunk(retriever):
    assert retriever.count() == 116


def test_rebuild_replaces_rather_than_duplicates(retriever, chunks):
    assert retriever.build(chunks) == 116
    assert retriever.count() == 116


def test_search_returns_ranked_scored_passages(retriever, chunks):
    target = next(c for c in chunks if c.chunk_id == "DOC-DEPLOY-001#symptoms")
    ps = retriever.search(target.text, top_k=5)
    assert ps[0].chunk_id == "DOC-DEPLOY-001#symptoms"
    assert len(ps) == 5
    assert [p.score for p in ps] == sorted((p.score for p in ps), reverse=True)
    assert all(-1.0 <= p.score <= 1.0 + 1e-6 for p in ps)


def test_passages_resolve_to_real_corpus_text(retriever, corpus):
    contents = {d["doc_id"]: d["content"] for d in corpus}
    for p in retriever.search("invoice usage charges higher than expected", top_k=5):
        assert p.text in contents[p.doc_id]


def test_threshold_returns_nothing_rather_than_something_irrelevant(retriever):
    assert retriever.search("zzzz qqqq xxxx", top_k=5, threshold=0.5) == []
    assert retriever.search("invoice usage charges", top_k=5, threshold=0.99) == []


@pytest.mark.parametrize("query,k", [("", 5), ("   \n", 5), ("invoice", 0)])
def test_empty_query_or_zero_k_returns_empty(retriever, query, k):
    assert retriever.search(query, top_k=k) == []


def test_top_k_larger_than_index_is_capped(retriever):
    assert len(retriever.search("deployment", top_k=10_000)) == 116


def test_get_chunk_resolves_citations(retriever, chunks):
    target = next(c for c in chunks if c.chunk_id == "DOC-AUTH-004#resolution")
    p = retriever.get_chunk("DOC-AUTH-004#resolution")
    assert p is not None and p.text == target.text and p.doc_id == "DOC-AUTH-004"
    assert retriever.get_chunk("DOC-FAKE-999#resolution") is None


def test_search_without_index_raises_unavailable(tmp_path):
    r = Retriever(FakeEmbedder(), tmp_path / "empty")
    with pytest.raises(RetrievalUnavailable):
        r.search("anything")


def test_embedder_mismatch_is_detected(tmp_path, chunks):
    path = tmp_path / "chroma"
    Retriever(FakeEmbedder(), path).build(chunks)

    class Other(FakeEmbedder):
        name = "different-model"

    with pytest.raises(RetrievalUnavailable, match="rebuild"):
        Retriever(Other(), path).search("invoice")


def test_best_score_per_doc_keeps_maximum():
    mk = lambda cid, s: Passage(chunk_id=cid, doc_id=cid.split("#")[0], title="", section="", text="", score=s)
    assert best_score_per_doc([mk("D-A#x", 0.4), mk("D-A#y", 0.7), mk("D-B#x", 0.5)]) == {"D-A": 0.7, "D-B": 0.5}


# --- integration: the real embedding model -------------------------------------------------

@pytest.fixture(scope="module")
def real_retriever(tmp_path_factory, chunks):
    try:
        from src.retrieve import SentenceTransformerEmbedder
        emb = SentenceTransformerEmbedder("all-MiniLM-L6-v2")
        emb.encode(["warm up"])
    except Exception as exc:  # offline / model not cached
        pytest.skip(f"embedding model unavailable: {exc}")
    r = Retriever(emb, tmp_path_factory.mktemp("real") / "chroma")
    r.build(chunks)
    return r


@pytest.mark.parametrize("query,expected_doc", [
    # Ines's example (Interview 4): keyword search cannot connect these two phrasings.
    ("my deployment keeps dying", "DOC-DEPLOY-001"),
    ("Our invoice this month is considerably higher than usual and I cannot see why", "DOC-BILL-001"),
    ("Where is our data stored? We need it to stay in the EU", "DOC-DATA-003"),
])
def test_known_questions_retrieve_the_right_article(real_retriever, query, expected_doc):
    ps = real_retriever.search(query, top_k=5, threshold=0.40)
    assert ps and ps[0].doc_id == expected_doc


def test_off_topic_text_is_filtered_by_threshold(real_retriever):
    assert real_retriever.search("I want a dark mode in the console", top_k=5, threshold=0.40) == []
    assert real_retriever.search("asdfgh qwerty zxcv", top_k=5, threshold=0.40) == []
