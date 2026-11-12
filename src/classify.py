"""Local intent and urgency classifier (A3). No language model is involved.

Design: sentence embeddings (the same local model retrieval uses) feed two logistic-regression
heads, one for intent (22 classes) and one for urgency (3 classes). Stated confidence is checked
against out-of-fold accuracy on development data (governance condition: within 5 points).

Why local rather than an LLM: the output is deterministic (A5), it can be calibrated, it is fast
and free, and it keeps working when the model provider is down (A11).

Known limit, found in discovery of the labels: identical tickets carry different urgency labels
in the development data, so urgency cannot be predicted well from text. See
`evaluation/results/classifier_sweep_dev.md` for the measured figures.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

from .models import Ticket
from .retrieve import Embedder

EMPTY_INTENT = "unclear_request"  # an empty ticket cannot be classified; treat it as unclear


class Alternative(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: str
    confidence: float


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)

    intent: str
    intent_confidence: float
    alternatives: tuple[Alternative, ...]   # next three intents after the prediction
    urgency: str
    urgency_confidence: float
    model_name: str
    model_version: str


def make_intent_head() -> LogisticRegression:
    """Multinomial logistic regression. C=64 was picked on development data because it gives the
    smallest gap between stated confidence and out-of-fold accuracy without changing accuracy
    (see evaluation/results/classifier_sweep_dev.md). A sigmoid-calibrated wrapper was tried first
    and rejected: with 22 classes it reported about 69% confidence on predictions that were right
    99.8% of the time."""
    return LogisticRegression(C=64.0, max_iter=5000)


def make_urgency_head() -> CalibratedClassifierCV:
    return CalibratedClassifierCV(LogisticRegression(C=1.0, max_iter=3000), method="sigmoid", cv=5)


def to_classification(intent_classes: Sequence[str], intent_proba: np.ndarray,
                      urgency_classes: Sequence[str], urgency_proba: np.ndarray,
                      model_name: str, model_version: str) -> Classification:
    order = np.argsort(intent_proba)[::-1]
    top = order[0]
    u = int(np.argmax(urgency_proba))
    return Classification(
        intent=str(intent_classes[top]),
        intent_confidence=round(float(intent_proba[top]), 4),
        alternatives=tuple(Alternative(value=str(intent_classes[i]), confidence=round(float(intent_proba[i]), 4))
                           for i in order[1:4]),
        urgency=str(urgency_classes[u]),
        urgency_confidence=round(float(urgency_proba[u]), 4),
        model_name=model_name,
        model_version=model_version,
    )


class TicketClassifier:
    MODEL_NAME = "embeddings+calibrated-logreg"

    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self.intent_head: LogisticRegression | None = None
        self.urgency_head: CalibratedClassifierCV | None = None
        self.version = "untrained"

    # --- training --------------------------------------------------------------------------

    def fit(self, tickets: Sequence[Ticket]) -> "TicketClassifier":
        rows = [t for t in tickets if t.labels and not t.is_empty
                and t.labels.get("intent") and t.labels.get("urgency")]
        if len(rows) < 50:
            raise ValueError(f"need at least 50 labelled tickets to train, got {len(rows)}")
        X = np.asarray(self.embedder.encode([t.text for t in rows]))
        self.intent_head = make_intent_head().fit(X, [t.labels["intent"] for t in rows])
        self.urgency_head = make_urgency_head().fit(X, [t.labels["urgency"] for t in rows])
        digest = hashlib.sha256("|".join(sorted(t.ticket_id for t in rows)).encode()).hexdigest()[:8]
        self.version = f"{self.embedder.name}-n{len(rows)}-{digest}"
        return self

    @property
    def is_trained(self) -> bool:
        return self.intent_head is not None and self.urgency_head is not None

    # --- inference -------------------------------------------------------------------------

    def predict_many(self, tickets: Sequence[Ticket]) -> list[Classification]:
        if not self.is_trained:
            raise RuntimeError("classifier is not trained; run `python -m scripts.train_classifier`")
        out: list[Classification | None] = [None] * len(tickets)
        idx = [i for i, t in enumerate(tickets) if not t.is_empty]
        if idx:
            X = np.asarray(self.embedder.encode([tickets[i].text for i in idx]))
            ip, up = self.intent_head.predict_proba(X), self.urgency_head.predict_proba(X)
            for row, i in enumerate(idx):
                out[i] = to_classification(self.intent_head.classes_, ip[row],
                                           self.urgency_head.classes_, up[row],
                                           self.MODEL_NAME, self.version)
        for i, c in enumerate(out):
            if c is None:  # empty ticket: no text to classify, zero confidence forces escalation
                out[i] = Classification(intent=EMPTY_INTENT, intent_confidence=0.0, alternatives=(),
                                        urgency="medium", urgency_confidence=0.0,
                                        model_name=self.MODEL_NAME, model_version=self.version)
        return out  # type: ignore[return-value]

    def predict(self, ticket: Ticket) -> Classification:
        return self.predict_many([ticket])[0]

    # --- persistence -----------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        if not self.is_trained:
            raise RuntimeError("nothing to save: classifier is not trained")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"intent": self.intent_head, "urgency": self.urgency_head,
                     "version": self.version, "embedder": self.embedder.name}, path)

    @classmethod
    def load(cls, path: str | Path, embedder: Embedder) -> "TicketClassifier":
        blob = joblib.load(path)
        if blob.get("embedder") != embedder.name:
            raise RuntimeError(f"classifier was trained with embedder '{blob.get('embedder')}', "
                               f"but '{embedder.name}' is configured; retrain it")
        clf = cls(embedder)
        clf.intent_head, clf.urgency_head, clf.version = blob["intent"], blob["urgency"], blob["version"]
        return clf
