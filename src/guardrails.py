"""Guardrails (A7, FR-07): every drafted answer is checked, and any failed check blocks it.

A blocked answer is never sent. The pipeline escalates the ticket with its context packet
instead. The checks are plain rules, so the same draft always gets the same verdict:

- pii              no email addresses, phone numbers, card numbers or secrets in the reply
- grounding        every citation is one of the passages that was actually retrieved, and the
                   reply cites at least one
- forbidden_claims no promise of refunds or credits, no "fixed on our side", no fix dates
- injection        the ticket must not try to instruct the system, and the reply must not leak
                   or follow such instructions
- tone             the reply is a sensible length and not shouting
- confidence       the model itself said it could answer from the passages
"""
from __future__ import annotations

import re
from typing import Sequence

from pydantic import BaseModel, ConfigDict

from .generate import Draft
from .models import Ticket
from .retrieve import Passage

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<![\w.#-])\+?\d[\d\s().-]{8,16}\d(?![\w-])")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
SECRET = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,})"
    r"|(?i:\b(?:password|passwd|secret|api[_ -]?key|token)\s*[:=]\s*\S{6,})"
)

FORBIDDEN_CLAIMS = {
    "refund_or_credit": re.compile(
        r"(?i)\b(?:refund|credit|reimburse\w*|compensat\w*)\b.{0,40}\b(?:has been|have been|was|were|will be|is being|"
        r"are being|issued|applied|processed|on its way)\b"
        r"|\b(?:we|i)(?:'ve| have| will|'ll| are going to| can)\s+(?:refund|credit|reimburse|compensate)\w*"),
    "fixed_on_our_side": re.compile(
        r"(?i)\b(?:we|i|our (?:team|engineers))(?:'ve| have| has)?\s+(?:now\s+)?(?:fixed|resolved|corrected|patched|repaired)\b"
        r"|\b(?:has|have) been (?:fixed|resolved|corrected|patched) (?:on|at|from) our (?:side|end)\b"
        r"|\bfixed on our (?:side|end)\b"),
    "fix_date": re.compile(
        r"(?i)\b(?:fix(?:ed)?|resolved?|resolution|patch(?:ed)?|restored?|available|deployed|released)\b.{0,40}"
        r"\b(?:by|on|before|within|in)\s+(?:the\s+)?(?:next\s+)?(?:\d+\s+(?:minute|hour|day|week)s?|tomorrow|today|tonight|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|end of (?:the )?(?:day|week)|\d{1,2}(?:st|nd|rd|th)?\s+\w+)"),
}

INJECTION_IN_TICKET = re.compile(
    r"(?i)\b(?:ignore|disregard|forget|override)\b.{0,30}\b(?:previous|prior|above|earlier|all|your|the)\b.{0,20}"
    r"\b(?:instruction|prompt|rule|guideline|direction)s?\b"
    r"|\b(?:system prompt|developer mode|jailbreak)\b"
    r"|\byou are now\b|\bact as (?:an?|the)\b|\bpretend (?:to be|you are)\b"
    r"|\b(?:reveal|print|show|repeat)\b.{0,20}\b(?:your|the)\b.{0,15}\b(?:prompt|instructions|rules)\b"
    r"|\bnew instructions?\s*:")
INJECTION_IN_REPLY = re.compile(
    r"(?i)\b(?:system prompt|my instructions|as an ai(?: language model)?|i (?:have been|was) instructed)\b")

CITATION_IN_TEXT = re.compile(r"\[([A-Z]+-[A-Z]+-\d+#[a-z0-9-]+)\]")
MIN_ANSWER_CHARS, MAX_ANSWER_CHARS = 40, 2500


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def find_pii(text: str) -> list[str]:
    """Kinds of private data found in the text (empty list if none)."""
    found = []
    if EMAIL.search(text):
        found.append("email")
    if SECRET.search(text):
        found.append("secret")
    cards = [re.sub(r"\D", "", m.group(0)) for m in CARD.finditer(text)]
    if any(13 <= len(c) <= 19 and luhn_ok(c) for c in cards):
        found.append("card_number")
    # Long digit runs (13+ digits) are card-like or reference numbers, never phone numbers,
    # so they are removed before looking for phones.
    if any(9 <= len(re.sub(r"\D", "", m.group(0))) <= 15 for m in PHONE.finditer(CARD.sub(" ", text))):
        found.append("phone")
    return found


def redact_pii(text: str) -> str:
    """Mask private data, for log summaries and escalation packets."""
    text = EMAIL.sub("[email]", text)
    text = SECRET.sub("[secret]", text)
    text = CARD.sub(lambda m: "[card]" if luhn_ok(re.sub(r"\D", "", m.group(0))) else "[number]", text)
    return PHONE.sub(lambda m: "[phone]" if 9 <= len(re.sub(r"\D", "", m.group(0))) <= 15 else m.group(0), text)


class GuardrailReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    blocked_by: tuple[str, ...]          # names of the failed checks
    results: dict[str, str]              # check name -> "pass" or "fail: detail"
    pii_types: tuple[str, ...] = ()

    def as_log(self) -> dict[str, str]:
        return dict(self.results)


def validate(ticket: Ticket, draft: Draft, passages: Sequence[Passage]) -> GuardrailReport:
    results: dict[str, str] = {}
    answer = draft.answer

    pii = find_pii(answer)
    results["pii"] = f"fail: {', '.join(pii)}" if pii else "pass"

    retrieved = {p.chunk_id for p in passages}
    cited = set(draft.citations) | set(CITATION_IN_TEXT.findall(answer))
    unknown = sorted(cited - retrieved)
    if not cited:
        results["grounding"] = "fail: no citations"
    elif unknown:
        results["grounding"] = f"fail: cites passages that were not retrieved: {', '.join(unknown)}"
    else:
        results["grounding"] = "pass"

    claims = [name for name, pat in FORBIDDEN_CLAIMS.items() if pat.search(answer)]
    results["forbidden_claims"] = f"fail: {', '.join(claims)}" if claims else "pass"

    if INJECTION_IN_TICKET.search(ticket.text):
        results["injection"] = "fail: the ticket contains instructions aimed at the system"
    elif INJECTION_IN_REPLY.search(answer):
        results["injection"] = "fail: the reply refers to its own instructions"
    else:
        results["injection"] = "pass"

    letters = [ch for ch in answer if ch.isalpha()]
    if not MIN_ANSWER_CHARS <= len(answer) <= MAX_ANSWER_CHARS:
        results["tone"] = f"fail: reply length {len(answer)} is outside {MIN_ANSWER_CHARS}-{MAX_ANSWER_CHARS}"
    elif letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.5:
        results["tone"] = "fail: reply is mostly capital letters"
    else:
        results["tone"] = "pass"

    results["confidence"] = "pass" if draft.can_answer else "fail: the model said the passages do not answer the ticket"

    blocked = tuple(name for name, verdict in results.items() if verdict != "pass")
    return GuardrailReport(passed=not blocked, blocked_by=blocked, results=results, pii_types=tuple(pii))


DISCLOSURE = "This reply was drafted by an automated assistant using CloudServe's help articles."


def finalise_reply(draft: Draft, passages: Sequence[Passage]) -> str:
    """Add the automation disclosure and the list of source articles (FR-10)."""
    cited = set(draft.citations) | set(CITATION_IN_TEXT.findall(draft.answer))
    sources: dict[str, str] = {}
    for p in passages:
        if p.chunk_id in cited:
            sources.setdefault(p.doc_id, p.title)
    lines = [draft.answer, "", DISCLOSURE, "Sources: " + "; ".join(f"{t} ({d})" for d, t in sources.items()) + ".",
             "If this does not solve the problem, reply to this message and a support engineer will pick it up."]
    return "\n".join(lines)
