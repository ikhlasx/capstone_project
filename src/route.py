"""Deterministic routing (A5). Rules and thresholds only; no language model on this path.

Rules are applied in order, and the first one that matches decides. Every decision records
which rule fired and which thresholds were applied, so it can be explained from the log.

  0. empty ticket                                   -> escalate
  1. predicted intent is protected                  -> escalate   (FR-04)
  2. a protected intent is a close runner-up        -> escalate   (FR-04, safety margin)
  3. intent confidence below the threshold          -> escalate   (FR-05)
  4. billing ticket that disputes a charge          -> escalate   (FR-12)
  5. high-urgency live incident (database, latency) -> escalate   (optional, see RoutingConfig)
  6. data-residency question without DOC-DATA-003   -> escalate   (FR-13)
  7. no passage above the relevance threshold       -> escalate   (FR-03)
  8. otherwise                                      -> generate an answer
"""
from __future__ import annotations

import re
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from .classify import Classification
from .models import Ticket
from .retrieve import Passage

ALWAYS_ESCALATE = frozenset({"security_incident", "compliance_request", "feature_request", "unclear_request"})
INCIDENT_INTENTS = frozenset({"database_issue", "performance_degradation"})
RESIDENCY_INTENT = "data_residency"
RESIDENCY_DOC = "DOC-DATA-003"
BILLING_INTENT = "billing_query"

# A billing ticket is treated as a dispute only when it explicitly contests a charge or asks for
# money back (Daniel, Interview 3: "nothing automated should be making commitments about money").
# "Charges for a service I do not believe we use. Could you explain?" is NOT matched: 6 of its 8
# copies in the development set are labelled auto-respond, so the data treats it as an invoice
# question. No development ticket matches this rule; it is a safety net, and the forbidden-claims
# guardrail separately blocks any answer that promises money.
DISPUTE_PATTERNS = re.compile(
    r"(?i)\b("
    r"disput\w*|chargeback\w*|refund\w*|overcharg\w*|double[- ]?(?:bill|charg)\w*|"
    r"(?:incorrect|wrong|mistaken|erroneous)(?:ly)? (?:charge|charged|bill|billed|amount)|"
    r"(?:charged|billed) (?:us |me )?(?:twice|incorrectly|wrongly)|should not (?:have been|be) (?:charged|billed)|"
    r"(?:want|need|demand|request)\w* (?:our|my|the)? ?money back|credit (?:us|me|our account)"
    r")"
)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence_threshold: float = 0.80
    relevance_threshold: float = 0.40
    protected_margin: float = 0.15      # rule 2: a protected runner-up at or above this escalates
    dispute_rule: bool = True           # rule 4
    incident_rule: bool = False         # rule 5: off by default, see classifier_sweep_dev.md
    residency_rule: bool = True         # rule 6


class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["generate", "escalate"]
    rule: str
    reason: str
    threshold_applied: dict[str, float]
    requirement_ids: tuple[str, ...]


def is_billing_dispute(ticket: Ticket) -> bool:
    return bool(DISPUTE_PATTERNS.search(ticket.text))


def route(ticket: Ticket, c: Classification, passages: Sequence[Passage],
          cfg: RoutingConfig = RoutingConfig()) -> RouteDecision:
    thresholds = {"confidence": cfg.confidence_threshold, "relevance": cfg.relevance_threshold,
                  "protected_margin": cfg.protected_margin}

    def decide(action, rule, reason, reqs):
        return RouteDecision(action=action, rule=rule, reason=reason,
                             threshold_applied=thresholds, requirement_ids=reqs)

    if ticket.is_empty:
        return decide("escalate", "empty_ticket", "The ticket has no text to act on.", ("FR-01", "FR-05"))

    if c.intent in ALWAYS_ESCALATE:
        return decide("escalate", "protected_intent",
                      f"Intent '{c.intent}' is always handled by a person.", ("FR-04",))

    for alt in c.alternatives:
        if alt.value in ALWAYS_ESCALATE and alt.confidence >= cfg.protected_margin:
            return decide("escalate", "possible_protected_intent",
                          f"Protected intent '{alt.value}' is a close alternative "
                          f"({alt.confidence:.2f} >= {cfg.protected_margin:.2f}).", ("FR-04",))

    if c.intent_confidence < cfg.confidence_threshold:
        return decide("escalate", "low_confidence",
                      f"Intent confidence {c.intent_confidence:.2f} is below "
                      f"{cfg.confidence_threshold:.2f}.", ("FR-05",))

    if cfg.dispute_rule and c.intent == BILLING_INTENT and is_billing_dispute(ticket):
        return decide("escalate", "billing_dispute",
                      "The ticket contests a charge; money decisions stay with a person.", ("FR-12",))

    if cfg.incident_rule and c.intent in INCIDENT_INTENTS and c.urgency == "high":
        return decide("escalate", "high_urgency_incident",
                      f"High-urgency '{c.intent}' is treated as a live incident.", ("FR-09",))

    relevant = [p for p in passages if p.score >= cfg.relevance_threshold]

    if cfg.residency_rule and c.intent == RESIDENCY_INTENT and not any(p.doc_id == RESIDENCY_DOC for p in relevant):
        return decide("escalate", "residency_without_source",
                      f"Data-residency question without {RESIDENCY_DOC} above the relevance threshold.",
                      ("FR-13",))

    if not relevant:
        return decide("escalate", "no_relevant_passage",
                      f"No documentation passage scored at or above {cfg.relevance_threshold:.2f}.",
                      ("FR-03",))

    return decide("generate", "answerable",
                  f"Intent '{c.intent}' at {c.intent_confidence:.2f} with {len(relevant)} relevant "
                  f"passage(s); best score {relevant[0].score:.2f}.", ("FR-05", "FR-06"))
