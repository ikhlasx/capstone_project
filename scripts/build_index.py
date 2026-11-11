"""Build (or rebuild) the Chroma index from the documentation corpus.

Usage:  python -m scripts.build_index [--docs data/documentation.json] [--chroma ./storage/chroma]
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter

from src.chunking import chunk_corpus, load_corpus
from src.config import get_settings
from src.retrieve import Retriever, SentenceTransformerEmbedder, corpus_fingerprint


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", default="data/documentation.json", help="documentation corpus (JSON list)")
    ap.add_argument("--chroma", default=s.chroma_path, help="Chroma persistence directory")
    args = ap.parse_args(argv)

    started = time.perf_counter()
    docs = load_corpus(args.docs)
    chunks = chunk_corpus(docs)
    retriever = Retriever(SentenceTransformerEmbedder(s.embedding_model), args.chroma)
    n = retriever.build(chunks)

    sections = Counter(c.section for c in chunks)
    print(f"indexed {n} chunks from {len(docs)} documents into {args.chroma}")
    print(f"sections: {dict(sections)}")
    print(f"embedder: {s.embedding_model}  fingerprint: {corpus_fingerprint(chunks)}  "
          f"time: {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
