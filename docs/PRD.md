# CloudServe Support Triage — Product Requirements Document

> **Draft v1.0, AI-assisted.** Claude drafted this from my discovery evidence, the course pack and
> the build so far. I review, edit and own every requirement, priority, target and assumption, and
> the AI assistance is listed in my AI-use declaration. Section 2 is copied from my discovery file.
> References `E1`–`E11` point to `discovery/evidence.md`. I still need to map each one to its
> Discovery Workbook section and row.

## 1. Document control

| Field | Value |
|---|---|
| Version | 1.0 |
| Written by | Ikhlas PV |
| Date | 6 November 2026 |
| Status | Draft for review |
| Approved by | |

## 2. The problem in one paragraph

*Copied from `discovery/problem_statement.md`. If it changes, I change it in the workbook first so the two never drift apart.*

You asked for a chatbot to bring the response-time number down without adding headcount. After going through the ticket data and speaking to the team, I think the response time is a symptom rather than the root cause. Seven in ten tickets already have an answer in your own help articles, but agents can't get to those answers quickly enough because the internal search is too literal — so they work from personal files or escalate. Nearly half of everything that reaches tier two is a question the articles already cover. Those tickets take about half a day instead of half an hour, customers rate them lower, and many write in a second time. The job is to get existing answers to customers at first contact, and to get the tickets that genuinely need a person to that person with the background already written up.

## 3. Who this is for

| User group | What they need | What they do today | How we'll know it worked |
|---|---|---|---|
| **Customers** | A quick, correct answer when one already exists. They want to be told when a reply is automated and where it came from, so they know how far to trust it (Ravi, Int. 5). | Search the docs themselves, find the answer about half the time, then wait hours for the same thing (Ravi). Answerable tickets that get escalated take a median of 717 minutes (E11). | Answerable tickets get a correct reply at first contact. No confidently wrong answers in the reviewed sample. Every automated reply says it's automated and names its source. |
| **Tier one agents** | Fewer repeat questions, and the right article already attached when a ticket does reach them (Sofia, Int. 2). | Work the queue oldest-first and copy from personal answer files, because searching the docs is "painful" (Sofia). | Fewer answerable tickets in the human queue. Every ticket that reaches them has the relevant article attached. |
| **Tier two engineers** | Escalations that arrive with a summary, the likely issue, what's already known, and the sources (Daniel, Int. 3). | Get "the original ticket, forwarded" and have to re-ask customers things they've already answered (Daniel). | Every escalation arrives with a complete context packet. Answerable tickets make up far less than today's 49% of escalations (E1). |
| **Head of support** | Better first-contact resolution and fewer escalations without hiring, and decisions he can explain at the autumn compliance review (Marcus, Int. 1). | Reports a breached two-hour promise (eight to twelve hours in practice) and pays roughly four times as much for every escalated ticket (Marcus). | First-contact resolution at 60% or above and escalations at 30% or below (brief §07). Any decision can be traced back from the log. |
| **Technical writer** | To see which article each answer came from, so she can tell a wrong article from a misread one (Ines, Int. 4). | Can't see how her articles get used. Agents rebuild them from memory (Ines). | Every automated answer cites passages from her articles, and those citations check out at least 95% of the time. |

## 4. Functional requirements

**Must** means the system isn't acceptable without it. **Should** means expected, and can be deferred if I state the consequence. **Will not** means considered and deliberately left out.

| ID | Requirement | Priority | Discovery evidence | Acceptance criteria |
|---|---|---|---|---|
| FR-01 | The system shall take tickets from email, chat, docs comments and the forum, and turn them into one standard ticket record. A missing or empty field must never stop the batch. | Must | E1 channel split (email 212, chat 155, docs comments 78, forum 55). Chat tickets have no subject line. | All 580 development and validation tickets load with no errors. Broken records are reported and skipped, not fatal. |
| FR-02 | The system shall label every ticket with one of 22 issue types and one of 3 urgency levels, along with how confident it is and its next three best guesses. | Must | E8 issue mix; E7 urgency | Issue-type precision of 85% or better (brief §07), reported for every type with a confusion matrix. |
| FR-03 | The system shall find the documentation passages most relevant to each ticket, score them, and return nothing at all when no passage is relevant enough. | Must | E1: 71% of tickets are answerable from the 29 articles. Ines, Int. 4: keyword search can't connect "my deployment keeps dying" to the health-check article. | Every returned passage traces back to real article text. On development data, the expected article is in the top five for 93.0% of tickets at a 0.40 threshold. Validation is reported separately. |
| FR-04 | Security incidents, compliance requests, feature requests and unclear requests shall always go to a person, however confident the system is. | Must | E8: these four types carry all 87 "must not auto-respond" labels. Sofia, Daniel and Ines all name them. | Zero automated replies to protected tickets in every evaluation run. |
| FR-05 | Whether a ticket is answered or escalated shall be decided by fixed rules and thresholds, never by the language model. | Must | Marcus, Int. 1: he must be able to explain why the system did what it did. | The same ticket always gets the same route. The model is never called when deciding the route. Thresholds come from a sweep on development data and are written down here. |
| FR-06 | The system shall write answers only from the passages it retrieved, and shall cite those passages for every claim. | Must | Ines, Int. 4; Ravi, Int. 5 ("here is the page it came from") | Every citation is one of the passages actually retrieved, checked automatically. At least 95% of citations support their sentence in a human-reviewed sample. |
| FR-07 | Every drafted answer shall be checked before it is sent, and blocked (with the ticket escalated instead) if it contains private data, cites something that wasn't retrieved, makes a forbidden promise, or shows signs that the ticket tried to give the system instructions. | Must | Marcus, Int. 1: "rather it said nothing than said something wrong". Expert answers forbid saying a refund has been issued, the issue has been fixed on our side, or a fix will arrive on a specific date. | At least one check is shown blocking in the tests. Zero private data in any outgoing reply (brief §07). |
| FR-08 | Every escalation shall carry a context packet: a short summary, the likely issue and urgency, the retrieved passages, why it was escalated, and what the system was unsure about. | Must | Daniel, Int. 3: escalations arrive with no summary. | Every escalation in a full run has every packet field filled in. |
| FR-09 | Escalated tickets shall be queued by urgency first, then by age. | Must | E7: high-urgency tickets take 342 minutes against 132 for low. Sofia sorts by age only. Ravi: a failing deployment costs far more than a pagination question. | The escalation queue is ordered high, medium, low, and oldest first within each. Covered by a test. |
| FR-10 | Every automated reply shall say that it was drafted by an automated assistant and name the article it came from. | Must | Ravi, Int. 5: knowing it's automated is how he decides whether to double-check. "Hiding that would be the thing that annoys me." | Every automated reply contains the disclosure line and at least one valid citation. |
| FR-11 | Every automated decision shall be logged: what came in, what was predicted, how confident, the alternatives, the sources used, the threshold applied, the action taken, the reason, and which requirements it serves. | Must | Marcus, Int. 1: compliance review. The Governance Framework's minimum record. | Logged decisions match processed tickets one to one at every stage. |
| FR-12 | Billing tickets that dispute a specific charge shall go to a person. | Should | Daniel, Int. 3: "nothing automated should be making commitments about money". Three billing tickets are labelled for escalation, e.g. DEV-0073 ("charges on our invoice for a service I do not believe we use"). | Not settled yet (Q1). A keyword rule on dispute, refund, chargeback or overcharged matches none of the 500 development tickets, so the method is chosen and measured in step 4. |
| FR-13 | Data-residency questions shall be answered automatically only when the residency article (DOC-DATA-003) is retrieved above the threshold. Everything else escalates. | Should | Daniel, Int. 3: mistakes here become compliance problems. E8: residency tickets are escalated 69% of the time today. | This departs from Daniel's advice to escalate all of them, so it needs justifying (Q2). No residency reply goes out without a DOC-DATA-003 citation. |
| FR-14 | The system shall process a whole ticket file from any location without anyone watching, and write a metrics report at the end. | Must | Build Specification | One command runs the full validation set unattended and writes `metrics.json` and `metrics.md`. |
| FR-15 | A conversational chatbot for customers. | Will not | The problem is getting existing answers to people, not the lack of a chat window. | — |
| FR-16 | Writing or revising help articles, or merging agents' personal answer files. | Will not | The articles belong to Ines (Int. 4). | — |

### How the requirements map to the build

| Requirement | Build Specification check | Build step | Status |
|---|---|---|---|
| FR-01 | A2 | Step 2: ingest | Done: 54 tests passing |
| FR-03 | A4 | Step 3: retrieval | Done: 29 tests passing, threshold sweep on development data |
| FR-02, FR-04, FR-05, FR-09, FR-11, FR-12, FR-13 | A3, A5, A8 | Step 4: classifier, routing, decision log | Next |
| FR-06, FR-07, FR-08, FR-10 | A6, A7 | Step 5: generator and guardrails | To do |
| FR-14 | A9, A10 | Step 6: full unattended run | To do |

## 5. Non-functional requirements

| ID | Category | Requirement | How it will be checked |
|---|---|---|---|
| NFR-01 | Latency | Deciding what to do with a ticket takes under 3 seconds at the 95th percentile. Total time including drafting an answer is reported separately. | The harness times every ticket and reports the median and 95th percentile. |
| NFR-02 | Availability | If the model provider times out, goes down, rate-limits us or sends back nonsense, the run carries on and the ticket escalates with its packet. Labelling and search run locally, so they keep working regardless. | Failure tests: no key, timeout, rate limit, empty ticket, garbage reply. The brief's target is 99.5% availability. |
| NFR-03 | Accuracy | When the classifier says it is 80% sure, it should be right about 80% of the time (within 5 points). Unsupported claims in 5% of answers or fewer. Citations correct 95% of the time or more. | A calibration table on development and validation data. At least 50 answers reviewed by two people, with how often they agreed reported. |
| NFR-04 | Privacy | No private data (email addresses, phone numbers, keys, card numbers) in any outgoing reply. No API key anywhere in the code or its history. | Tests for the private-data check. A secret scan of the repository before submission. |
| NFR-05 | Auditability | Any automated decision can be reconstructed from the log, with one row per stage per ticket. | The harness checks that logged decisions match processed tickets. |
| NFR-06 | Fairness | Less than a 5-point gap between customer groups (plan tier, region, language fluency) in routing accuracy and search accuracy. | The harness splits results by group and flags any gap over 5 points. **Already found: search finds the right article for 94.8% of fluent tickets but only 87.4% of non-fluent ones, a 7.4-point gap.** |
| NFR-07 | Cost | Runs on free-tier models. Repeated calls are cached, so re-running doesn't spend the rate limit again. | Cost per run and cache hits are recorded in the report. |
| NFR-08 | Reproducibility | Anyone can run it from a fresh copy by following the README. Tests run with one command. | Clone into an empty folder and follow the README word for word. `python -m pytest tests/ -v` |

## 6. What is deliberately out of scope

| Not building | Why not | What would make me reconsider |
|---|---|---|
| Automated replies to security, compliance, feature and unclear tickets | All 87 "must not auto-respond" labels sit in these four types (E8). Feature and unclear tickets have no article to answer from (Ines, Int. 4). | A reviewed policy from security and compliance saying which cases are safe, plus articles that cover them. |
| A chatbot | The problem is getting existing answers to customers, not a missing chat window. | Evidence that customers are giving up on email and the forum in a way that hurts first-contact resolution. |
| Writing articles or merging personal answer files | That's Ines's job, and it doesn't fit a three-week build. | The log shows the same "no relevant article" escalation coming up again and again. |
| Promising refunds, credits or fix dates | These are contractual decisions (Daniel, Int. 3), and the expert answers forbid them. | Never. These stay with a person. |
| Answering brand-new incidents | There's no article yet, and that's where a wrong answer does the most damage (Ines, Int. 4). | — |

## 7. Assumptions and their consequences

| Assumption | Why I believe it | What happens if it's wrong | How I'll find out |
|---|---|---|---|
| A1. A relevance threshold can tell tickets that have a matching article apart from tickets that don't. | Off-topic text scores around 0.1, while relevant text scores 0.45 to 0.67. | Tickets with no article get passed to the answer generator, so routing has to lean on the issue-type rules instead. | The retrieval sweep. **Tested in step 3 and found false:** only 14.7% of no-article tickets come back empty at 0.40. Goes in the Stage 5 revision log. |
| A2. The dataset's "answerable" and "expected article" labels are correct. | They come with the pack, and they match Sofia's own estimate that seven in ten tickets are ones she already knows (Int. 2). | My search and routing scores are measured against the wrong answers. | Check 30 tickets by hand against the articles. |
| A3. Resolution time is a fair stand-in for how long customers wait. | It's the only time field in the data. | The urgency finding (E7) describes time to resolve, not time to first reply. | State the limitation, and compare with Marcus's eight-to-twelve-hour first-reply figure. |
| A4. The 29 articles are current and correct. | Ines reviews them on a rotation (Int. 4). | Correct search and correct citations would still give wrong answers. | Note how long ago each article was reviewed and flag old ones. |
| A5. 500 development tickets are enough to train and calibrate a 22-type classifier. | Most types have 15 to 30 examples. | Rare types are unreliable, and calibration misses the 5-point condition. | Per-type precision and a calibration table in step 4. |
| A6. The free-tier model is reliable enough for an unattended run over the whole set. | A live test call came back in under 2 seconds (step 1). | Rate limits stop the run partway through. | The first full run in step 6. Retries, back-off and caching cover it (NFR-02). |
| A7. The hidden test set looks like the development and validation sets. | Same channels and the same labels. | Thresholds tuned on development data don't carry over. | Compare development and validation results. The hidden set is used once. |

## 8. Success measures

The brief's baselines don't match the development data. **I need to decide which one I report, and say why.**

| Measure | Baseline (brief / Marcus) | Baseline (my data, 500 tickets) | Target | Measured how | Reported by |
|---|---|---|---|---|---|
| First-contact resolution | 42% | 44% (E1) | 60% or better | Tickets closed without escalation ÷ all tickets | Ikhlas PV, in `metrics.md` |
| Time to first reply | 8 to 12 hours | 48-minute median resolution for answerable tickets (E2), a stand-in only | Under 5 minutes | System response time per ticket | Ikhlas PV |
| Customer satisfaction | 3.2 / 5 | 2.97 (E1) | 4.0 or better | A sample of replies scored against a rubric, with method and reviewers stated | Ikhlas PV |
| Escalation rate | 58% | 56% (E1) | 30% or lower | Tickets sent to a person ÷ all tickets | Ikhlas PV |
| Repeat contacts | Not measured | 22% (E1) | Halved | Stand-in: automated replies that miss what the expert answer says they must mention, or say something it forbids | Ikhlas PV |
| Automated replies to protected tickets | — | 87 protected tickets | 0 | Counted in every run | Ikhlas PV |

## 9. Open questions

| Question | Why it matters | Owner | Resolve by |
|---|---|---|---|
| Q1. How does the system tell a billing *dispute* apart from an ordinary billing *question*? | Keyword rules catch none of them, and a missed dispute would get an automated reply (FR-12). | Ikhlas PV | Step 4 |
| Q2. Should residency questions always escalate, as Daniel says, or be answered when DOC-DATA-003 is cited (FR-13)? | A wrong answer is a compliance problem, and the plan goes against stakeholder advice. | Ikhlas PV | Step 4 |
| Q3. What relevance threshold and confidence threshold should I use? | They set the balance between answering more tickets and staying safe. | Ikhlas PV | Steps 3–4 |
| Q4. What do I do about the 7.4-point fluency gap in search? | It breaks the under-5-point fairness condition (NFR-06). | Ikhlas PV | Step 6 |
| Q5. Which baseline do I report: the brief's (42%, 58%, 3.2) or my data's (44%, 56%, 2.97)? | It changes how the improvement looks. | Ikhlas PV | Before the report |
| Q6. Should enterprise tickets be handled any differently? | Marcus and Ravi both expect a widening gap to be noticed (Int. 1, Int. 5). | Ikhlas PV | Step 6 |
