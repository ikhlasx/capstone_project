"""Retrieval over the documentation corpus (A4).

- Embeds section chunks locally with sentence-transformers. There is no network call at query
  time, so retrieval keeps working when the LLM provider is down (A11).
- Stores the chunks in a persistent Chroma collection using cosine distance.
- `search` returns ranked passages with a similarity score in [-1, 1], where higher is closer.
  It applies a relevance threshold and returns an empty list rather than an irrelevant passage.
- `get_chunk` resolves a chunk id back to its verbatim corpus text, so citations can be checked
  (A6).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol, Sequence

from pydantic import BaseModel, ConfigDict

from .chunking import Chunk

COLLECTION = "cloudserve_docs"


class Embedder(Protocol):
    name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one L2-normalised vector per text."""
        ...


class SentenceTransformerEmbedder:
    """Local embedding model. The model loads on the first call, so importing this module stays cheap."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.name = model_name
        self._model = None

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name)
        vecs = self._model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()


class Passage(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str
    doc_id: str
    title: str
    section: str
    text: str
    score: float


class RetrievalUnavailable(RuntimeError):
    """The index is missing or empty. Run `python -m scripts.build_index` first."""


def corpus_fingerprint(chunks: Sequence[Chunk]) -> str:
    payload = json.dumps([[c.chunk_id, c.embed_text] for c in chunks], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class Retriever:
    def __init__(self, embedder: Embedder, chroma_path: str | Path, collection: str = COLLECTION):
        import chromadb
        from chromadb.config import Settings

        self.embedder = embedder
        self.collection_name = collection
        self._client = chromadb.PersistentClient(
            path=str(chroma_path), settings=Settings(anonymized_telemetry=False))

    # --- index -----------------------------------------------------------------------------

    def build(self, chunks: Sequence[Chunk]) -> int:
        """(Re)build the collection from scratch. Returns the number of chunks indexed."""
        if not chunks:
            raise ValueError("no chunks to index")
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass  # did not exist yet
        col = self._client.create_collection(
            self.collection_name,
            metadata={"hnsw:space": "cosine", "embedder": self.embedder.name,
                      "fingerprint": corpus_fingerprint(chunks)},
        )
        col.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=self.embedder.encode([c.embed_text for c in chunks]),
            documents=[c.text for c in chunks],
            metadatas=[{"doc_id": c.doc_id, "title": c.title, "section": c.section} for c in chunks],
        )
        return col.count()

    def _collection(self):
        try:
            col = self._client.get_collection(self.collection_name)
        except Exception as exc:
            raise RetrievalUnavailable(
                f"collection '{self.collection_name}' not found; run `python -m scripts.build_index`"
            ) from exc
        if col.count() == 0:
            raise RetrievalUnavailable(f"collection '{self.collection_name}' is empty")
        meta = col.metadata or {}
        if meta.get("embedder") not in (None, self.embedder.name):
            raise RetrievalUnavailable(
                f"index was built with embedder '{meta.get('embedder')}', "
                f"but the configured embedder is '{self.embedder.name}'; rebuild the index")
        return col

    def count(self) -> int:
        return self._collection().count()

    # --- query -----------------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5, threshold: float | None = None) -> list[Passage]:
        """Top-k passages, best first. Passages scoring below `threshold` are dropped."""
        if not query or not query.strip() or top_k <= 0:
            return []
        col = self._collection()
        res = col.query(
            query_embeddings=self.embedder.encode([query]),
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        passages = [
            Passage(chunk_id=cid, doc_id=meta["doc_id"], title=meta["title"],
                    section=meta["section"], text=doc, score=round(1.0 - dist, 6))
            for cid, doc, meta, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]
        if threshold is not None:
            passages = [p for p in passages if p.score >= threshold]
        return sorted(passages, key=lambda p: p.score, reverse=True)

    def get_chunk(self, chunk_id: str) -> Passage | None:
        """Look up a chunk id, for the citation check. Returns None if the id is not in the corpus."""
        res = self._collection().get(ids=[chunk_id], include=["documents", "metadatas"])
        if not res["ids"]:
            return None
        meta = res["metadatas"][0]
        return Passage(chunk_id=res["ids"][0], doc_id=meta["doc_id"], title=meta["title"],
                       section=meta["section"], text=res["documents"][0], score=1.0)


def best_score_per_doc(passages: Sequence[Passage]) -> dict[str, float]:
    """Collapse chunk hits into one score per document, keeping the best-scoring chunk."""
    out: dict[str, float] = {}
    for p in passages:
        out[p.doc_id] = max(out.get(p.doc_id, float("-inf")), p.score)
    return out
