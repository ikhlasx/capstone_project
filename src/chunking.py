"""Section-aware chunking of the documentation corpus.

Chunking decision (record this in the report):
Every article in the corpus uses the same four level-two sections: Symptoms, Common causes,
Resolution and Notes. Each section is 11–103 words long. One chunk per section is used because:
- Sections are short, so a section never needs splitting and the passage stays readable.
- Sections have different jobs. "Symptoms" is phrased the way a customer describes a problem,
  so it is what a ticket usually matches. "Resolution" is what an answer cites. Keeping them
  separate lets a citation point at the exact part of the article that supports a claim.
- Chunk ids such as `DOC-DEPLOY-001#resolution` are stable and human-checkable, which makes the
  citation check (A6) a direct lookup.

The text stored for each chunk is a verbatim slice of the article, so every passage resolves
to real corpus text (A4). The article title and "applies to" line are prepended only to the
text that gets embedded, so a short section still carries what it is about.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

_SECTION = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: str      # e.g. DOC-AUTH-001#resolution
    doc_id: str
    title: str
    section: str       # heading as written, e.g. "Common causes"
    text: str          # verbatim section body from the article
    embed_text: str    # what gets embedded: title + applies-to + section + text


def slugify(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-") or "section"


def chunk_document(doc: dict[str, Any]) -> list[Chunk]:
    doc_id = doc["doc_id"]
    title = (doc.get("title") or "").strip()
    applies = (doc.get("applies_to") or "").strip()
    content = doc.get("content") or ""

    context = title + (f" (applies to: {applies})" if applies else "")
    matches = list(_SECTION.finditer(content))

    if not matches:  # no sections: the whole article is one passage
        body = content.strip()
        return [Chunk(chunk_id=f"{doc_id}#body", doc_id=doc_id, title=title, section="body",
                      text=body, embed_text=f"{context}\n{body}")] if body else []

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[m.end():end].strip()
        if not body:
            continue
        slug = slugify(heading)
        seen[slug] = seen.get(slug, 0) + 1
        if seen[slug] > 1:  # repeated heading inside one article
            slug = f"{slug}-{seen[slug]}"
        chunks.append(Chunk(
            chunk_id=f"{doc_id}#{slug}", doc_id=doc_id, title=title, section=heading,
            text=body, embed_text=f"{context}\n{heading}\n{body}",
        ))
    return chunks


def load_corpus(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of documents")
    return data


def chunk_corpus(docs: list[dict[str, Any]]) -> list[Chunk]:
    chunks = [c for d in docs for c in chunk_document(d)]
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate chunk ids: {dupes}")
    return chunks
