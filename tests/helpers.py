"""Shared test helpers."""
from __future__ import annotations

import hashlib
import math
import re


class FakeEmbedder:
    """Hashed bag-of-words, L2-normalised. Shared words mean a higher cosine score."""

    name = "fake-bow-256"

    def encode(self, texts):
        out = []
        for text in texts:
            v = [0.0] * 256
            for w in re.findall(r"[a-z0-9]+", text.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out
