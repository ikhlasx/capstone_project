# Problem Statement

## Six-element table

| Element | Statement | Workbook row |
|---|---|---|
| **What the client asked for** | A chatbot to handle the easy tickets so agents can focus on the hard ones, without hiring more people. | Section 1, stakeholder table → *Marcus Adeyemi, Head of Support* |
| **What they actually need** | A way to get answers that already exist in the 29 help articles to customers at first contact (71% of tickets are already answerable), and to send everything else to a specialist with the ticket context already written up. | Section 2, ticket-data table → *Proportion answerable from existing documentation* |
| **The gap** | 138 of the 357 answerable tickets were escalated anyway — 49% of all 281 escalations. First-contact resolutions of answerable tickets: median 32 min, 3.41 CSAT, 0% repeat contacts. The same tickets escalated: median 717 min, 2.56 CSAT, 42% repeat contacts (E11). | Section 2, ticket-data table → *Proportion answerable from existing documentation*; *Proportion marked resolved on first contact*; *Proportion that are repeat contacts* |
| **Who is affected** | Customers: urgent tickets take longest to resolve (median 342 min vs 132 for low urgency, E7). Ravi finds the answer himself then receives the same answer hours later and has wasted two hours. Sofia can't navigate the docs fast enough so she copies from a personal answer file that may be out of date. Daniel re-interviews customers because escalations arrive with no context, and flags that even tier-two engineers get data-residency questions wrong. Marcus pays roughly four times as much per escalated ticket. | Section 1, stakeholder table → all five rows; Section 2, ticket-data table → *Split by urgency* |
| **What changes if this is solved** | First-contact resolution rises from 44% to ≥60%; escalations fall from 56% to ≤30%. All 87 protected tickets go to a person with context. Billing queries that dispute specific invoice charges, and data-residency questions the system cannot answer with high confidence, also go to a person. | Section 4, sentence-test table → rows 1 and 2; Section 2, ticket-data table → baseline rows |
| **Not in scope** | Auto-answering the 87 protected tickets; automated responses to billing queries that dispute specific invoice charges; automated responses to data-residency questions below the confidence threshold; authoring or revising help articles. | Section 5, risk register → *The system answers confidently and incorrectly*; *Some customers get consistently worse answers*; Section 1, stakeholder table → *Daniel Okonkwo*; *Ines Varga* |

---

## Problem statement

### What was asked, and what is needed

CloudServe asked for a chatbot to answer the easy tickets so the six agents can get on with the hard ones, without hiring anyone (Marcus, Interview 1). After going through the 500 tickets and the five interviews, I don’t think a chat window is what’s missing. 71% of tickets are already answered in the company’s own 29 help articles. The answers exist; they just aren’t reaching customers quickly.

### Why they don’t

Ines explains it: the internal search matches on titles and exact terms, so a customer who writes “my deployment keeps dying” never finds the article called “resolving container health check failures” (Interview 4). Sofia says the documentation is fine and she simply can’t find things in it, so she copies from a personal file of past answers (Interview 2). Everyone has one. Ines has asked twice for them to be consolidated, and Daniel says some hold answers that stopped being correct two years ago (Interviews 3 and 4).

### What the data shows

357 of the 500 tickets were answerable from the docs. Tier one resolved 219 of them: median 32 minutes, satisfaction 3.41, no repeat contacts. The other 138 were escalated, nearly half of all 281 escalations: median 717 minutes, satisfaction 2.56, and 42% led to a second contact (E11). Escalated tickets may simply be harder, so I’m not claiming escalation caused the gap, but in both groups the answer was in the documentation. Urgent tickets also take longest to resolve (median 342 minutes against 132 for low urgency, E7), and Sofia works her queue oldest-first, so nothing puts urgent ones ahead.

### Who feels it

Ravi searches the docs himself, finds the answer about half the time, and says the reply that eventually arrives is usually the same thing, after he has burned two hours (Interview 5). Daniel gets escalations as the original ticket forwarded with no summary, so he re-reads the thread and re-asks customers things they’ve already been asked; he says that frustrates them more than the wait (Interview 3). Marcus reckons a ticket that bounces to tier two costs roughly four times a resolved one (Interview 1).

### Constraints

Marcus would rather the system said nothing than said something wrong. His compliance review this autumn means every decision must be explainable, and Ines wants each answer to show its source article so she can tell a bad article from a misread one. Marcus expects enterprise customers to notice any drop in service, and Ravi, on the business plan, says a wider gap with enterprise would come up at renewal.

### Success and scope

The aim is first-contact resolution rising from 44% to at least 60%, and escalations falling from 56% to 30% or lower. Marcus himself says 42%; the 65% is the industry benchmark people quote at him. The 87 protected tickets (security 26, compliance 26, feature requests 20, unclear 15) go to a person with context, and none get an automated reply. Billing disputes go to a person too, but how the system recognises a dispute is still an open question for Step 4. The three billing tickets labelled for escalation say things like “charges on our invoice for a service I do not believe we use”, and a keyword rule on dispute, refund, chargeback or overcharged matches none of the 500. Daniel says anything involving data location should escalate. My current plan is to auto-answer only when DOC-DATA-003 is found with high confidence, which departs from his advice, so I need to justify that or reverse it. Out of scope: auto-answering the protected tickets and writing or revising the help articles.

---

## One-paragraph version (for Marcus)

You asked for a chatbot to bring the response-time number down without adding headcount. After going through the ticket data and speaking to the team, I think the response time is a symptom rather than the root cause. Seven in ten tickets already have an answer in your own help articles, but agents can't get to those answers quickly enough because the internal search is too literal — so they work from personal files or escalate. Nearly half of everything that reaches tier two is a question the articles already cover. Those tickets take about half a day instead of half an hour, customers rate them lower, and many write in a second time. The job is to get existing answers to customers at first contact, and to get the tickets that genuinely need a person to that person with the background already written up.

---

## Transcript check

| Interviewee | Would they recognise it? | Any likely objection? |
|---|---|---|
| **Marcus Adeyemi** | Yes — the 4× cost figure, the FCR and escalation targets, and the "nothing rather than something wrong" constraint all come from his words. | The statement says the target is 60% FCR; Marcus quoted 65% as the industry benchmark, not as his own target. Worth clarifying in the workbook but not a material error here. |
| **Sofia Restrepo** | Yes — paragraph 3 uses her own framing: seven out of ten already known, the search problem, the personal answer file. | She might add that the tickets in a language other than English take longer and have the worst satisfaction scores. That's real but belongs in a constraint note rather than the main statement. |
| **Daniel Okonkwo** | Yes — the context-free escalation point and the data-residency warning are both his. The billing caveat in paragraph 5 follows his exact description of what makes billing escalations different. | None — paragraph 3 distinguishes his frustration (re-interviewing customers) from the volume, which is accurate to the transcript. |
| **Ines Varga** | Yes — she's named on the search problem and the article-citation requirement. The not-in-scope list covers article authorship. | She might note that agents reconstruct her articles from memory rather than copy them, which slightly understates the problem. Paragraph 3 says "copies from a personal answer file," which is accurate for Sofia; Ines's observation is a separate layer. |
| **Ravi Menon** | Yes — paragraph 3 uses the specific scenario he described: finds the answer himself, waits anyway, receives the same thing. The enterprise-tier gap he mentioned at the end of his interview is reflected in Marcus's enterprise constraint in paragraph 4. | None — the statement does not promise anything about automated responses to customers, which keeps it honest to what Ravi said he would actually accept. |
