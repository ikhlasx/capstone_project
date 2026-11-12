"""Train the intent and urgency classifier and save it.

Usage:  python -m scripts.train_classifier [--train data/development_tickets.json]
                                           [--out ./storage/models/classifier.joblib]
"""
from __future__ import annotations

import argparse
import sys
import time

from src.classify import TicketClassifier
from src.config import get_settings
from src.ingest import load_tickets
from src.retrieve import SentenceTransformerEmbedder


def main(argv: list[str] | None = None) -> int:
    s = get_settings()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", default=s.training_data, help="labelled tickets to train on")
    ap.add_argument("--out", default=s.classifier_path, help="where to save the trained model")
    args = ap.parse_args(argv)

    started = time.perf_counter()
    tickets = load_tickets(args.train).tickets
    clf = TicketClassifier(SentenceTransformerEmbedder(s.embedding_model)).fit(tickets)
    clf.save(args.out)
    print(f"trained on {len(tickets)} tickets from {args.train}")
    print(f"intents: {len(clf.intent_head.classes_)}  urgency levels: {len(clf.urgency_head.classes_)}")
    print(f"saved {args.out}  version: {clf.version}  time: {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
