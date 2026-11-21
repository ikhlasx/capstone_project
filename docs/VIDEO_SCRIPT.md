# Video Presentation Script: CloudServe Support Triage
**Presenter:** Ikhlas PV  
**Programme:** Forward Deployed AI Engineering  
**Target Video Duration:** 18:00 – 22:00 minutes (Target: exactly 20:00)  
**Pacing:** ~125 words per minute (gives comfortable time for terminal commands to execute)  

---

## Pre-Recording Checklist & VS Code Setup

Open your terminal in VS Code inside `e:\iit roorke\capstone` and run:

```powershell
# 1. Activate the Python virtual environment
.venv\Scripts\Activate.ps1

# 2. Verify all 230 tests pass cleanly
python -m pytest tests/ -v
```

### Video Recording Structure & Time Allocation Table

| Section | Time Slot | Window | What's on Screen | Core Focus |
|---|---|---|---|---|
| **1. The Problem** | 0:00 – 2:00 | 120s | Full Webcam (Face to camera) | Introduction, Marcus's dilemma, the 71% doc discovery |
| **2. What Discovery Showed** | 2:00 – 5:00 | 180s | Screen Share (`discovery/evidence.md`) | Inverted urgency (Table E7), escalation drain (Table E11) |
| **3. Architecture & Design** | 5:00 – 7:00 | 120s | Screen Share (`README.md` or Diagram) | 7-stage pipeline, deterministic routing without LLM |
| **4.1 Live Demo: Tests** | 7:00 – 8:00 | 60s | Terminal (Font size 16pt) | Run test suite (230 tests pass in ~25s) |
| **4.2 Live Demo: Grounded Answer** | 8:00 – 9:30 | 90s | Terminal | Case 1: Deployment failure finds `DOC-DEPLOY-001` |
| **4.3 Live Demo: Safe Escalation** | 9:30 – 10:45 | 75s | Terminal | Case 2: Protected compliance request escalates with packet |
| **4.4 Live Demo: Guardrails Blocking** | 10:45 – 12:15 | 90s | Terminal | Case 3: `python -m scripts.demo guardrail` blocks bad drafts |
| **4.5 Live Demo: Full Run & Audit Log** | 12:15 – 14:00 | 105s | Terminal | Run unattended harness on validation set & query SQLite DB |
| **5. What the Numbers Say** | 14:00 – 17:00 | 180s | Screen Share (`metrics.md`) | 77.5% auto-answered, 0 protected auto-replies, caveats |
| **6. Fairness & Failure Testing** | 17:00 – 18:00 | 60s | Screen Share (`metrics.md` Fairness) | Multi-axis audit, 25 failure-injection test scenarios |
| **7. What I Got Wrong & Closing** | 18:00 – 20:00 | 120s | Full Webcam (Face to camera) | 186-ticket urgency noise, calibration, closing reflection |

---

# SECTION 1: THE PROBLEM (0:00 – 2:00)
**[Camera: Full webcam, look directly into the lens. Speak naturally and warmly.]**

"Hi everyone, my name is Ikhlas PV, and this is my capstone engineering project for CloudServe Solutions.

To understand why I built what I built, you have to look at the situation CloudServe was facing. CloudServe sells cloud hosting and infrastructure to software engineers. Their head of support, Marcus Adeyemi, manages a team of six agents handling more than five hundred customer tickets every week. 

CloudServe’s service commitment to customers is a first response within two hours. But in reality, their response time was averaging between eight and twelve hours. Marcus had been reporting a red SLA metric to executive leadership for two straight quarters, and he was running out of ways to explain the backlog.

Naturally, leadership asked for a conversational AI chatbot—something to sit on the portal, converse with users, and handle routine tickets so human agents could focus on complex engineering issues.

When I dug into five hundred historical customer tickets and analyzed interviews with five key stakeholders, I realized that CloudServe didn’t actually have a chat problem. **Seventy-one percent of all incoming tickets already had clear, complete answers inside CloudServe’s own twenty-nine help articles.**

The answers already existed. But frontline agents couldn't find them quickly under pressure. So they either copied outdated snippets from personal text files, or they passed the ticket up to senior infrastructure engineers.

That escalation habit was devastating. An escalated ticket cost CloudServe roughly four times as much—about sixty-one dollars in diverted senior engineering time compared to fourteen dollars for a frontline resolution. And customers were left waiting for hours in secondary queues.

So I didn't build an open-ended conversational chatbot. I built an **Intelligent Support Triage System**. It automatically resolves tickets that the documentation already covers, and it deterministically routes everything else to human engineers with full context attached."

---

# SECTION 2: WHAT DISCOVERY SHOWED (2:00 – 5:00)
**[Camera: Switch to Screen Share. Open `discovery/evidence.md` in VS Code or browser.]**

"Let’s look at the actual empirical evidence from the 500 historical tickets that reshaped this project.

**[Scroll to Table E11: Escalation vs. Documentation Overlap]**

Look at Table E11. Out of five hundred historical tickets, three hundred and fifty-seven could be answered directly from the documentation. 

Tier one agents successfully resolved two hundred and nineteen of them at the frontline. For those, the median resolution time was thirty-two minutes, customer satisfaction was 3.41 out of 5, and not a single customer had to write back in.

Now look at the remaining one hundred and thirty-eight tickets. Even though the answers were written down in the documentation, frontline agents escalated them to senior engineers. That represents nearly half of all two hundred and eighty-one escalations. 

For those escalated tickets, resolution took a median of seven hundred and seventeen minutes—almost twelve hours! Customer satisfaction crashed to 2.56, and forty-two percent of those customers had to write back in asking for updates. These were different tickets, so I’m not claiming escalation alone caused the delay. But in both groups, the technical solution was already documented.

**[Scroll to Table E7: Inverted Urgency]**

Now, look at Table E7. This was the most shocking discovery: **the inverted urgency paradox**. 

In an efficient support organization, urgent outages are resolved first. At CloudServe, low-urgency administrative tickets took a median of one hundred and thirty-two minutes to resolve. High-urgency production outages took **three hundred and forty-two minutes**—nearly six hours! 

The tickets that mattered most took the longest to fix. Ravi, an infrastructure engineer and CloudServe customer, told us: *'If my deployment fails at 9:00 AM, waiting four hours is a crisis.'* He searches the docs himself, finds the answer about half the time, and when support finally replies hours later, they quote the exact doc he already read.

Internally, two operational bottlenecks caused this:
First, Sofia, a frontline agent, explained that she works her queue strictly oldest-first, meaning high-urgency production incidents don't bubble to the top. 
Second, Daniel in tier two told us that escalations reach him as raw, forwarded emails with no summary. He has to re-read the entire thread and often asks the customer questions they already answered, which frustrates customers more than the delay itself.

I also extracted three non-negotiable constraints from stakeholder interviews:
1. Marcus said: *'I would rather the system said nothing than said something wrong.'*
2. CloudServe faces an external compliance audit this autumn, so every routing decision must be mathematically explainable.
3. Ines, who authors the documentation, insisted that every answer must cite its exact article source.

That completely ruled out an unconstrained, free-running chatbot. The system had to be grounded, transparent, and deterministic."

---

# SECTION 3: ARCHITECTURE (5:00 – 7:00)
**[Camera: Screen Share. Show pipeline diagram in `README.md` or `docs/architecture.md`.]**

"To solve this, I designed a multi-stage triage and grounded generation pipeline built in seven distinct steps:

1. **Ingest:** Tickets arrive from four heterogeneous channels—web portal, email, live chat, and API webhooks. The ingest normalizer validates them into a strongly typed Pydantic contract. Missing fields or messy signatures are handled gracefully.
2. **Classify:** A local classifier predicts one of twenty-two operational intents and assesses urgency, producing a calibrated confidence probability. Because it runs locally using scikit-learn, it executes in single-digit milliseconds and continues working even if external cloud APIs go down.
3. **Retrieve:** CloudServe’s twenty-nine articles are split by section into one hundred and sixteen atomic chunks and indexed in a local Chroma vector database using bi-encoder embeddings. It searches by semantic meaning, not keyword matching. If no passage meets the 0.40 relevance floor, retrieval returns nothing.
4. **Route:** **This is the core architectural decision.** No language model decides whether a ticket is answered or escalated. Routing is handled by 100% deterministic Python rules. Protected intents like compliance, security incidents, legal holds, and account deletions always escalate. Low classifier confidence escalates. Missing documentation escalates.
5. **Generate:** For answerable tickets, an LLM drafts an answer using prompt `PR-01@1.0`. The prompt strictly forbids outside knowledge and mandates bracketed citations for every claim.
6. **Validate:** Before any reply leaves the system, an active guardrail firewall runs six checks, inspecting for PII, Luhn-validated credit card numbers, prompt injections, fabricated citations, and unauthorized refund promises.
7. **Audit Log:** Every classification, routing rule, passage score, and guardrail check is committed to an immutable SQLite database for complete SOC-2 auditability."

---

# SECTION 4: LIVE DEMONSTRATION (7:00 – 14:00)
**[Camera: Full Terminal window. Make font large (16pt), clear, and clean.]**

### 4.1 Demo: Test Suite (7:00 – 8:00)
"Let’s start with the automated test suite.

**[Type and run in terminal:]**
```powershell
python -m pytest tests/ -v
```

**[While tests run, speak calmly:]**
There are two hundred and thirty automated tests. They cover input normalization across all four channels, Chroma vector retrieval, deterministic routing rules, post-generation guardrails, edge-case failure injections like network timeouts and 401 errors, and the FastAPI endpoints.

**[Point at terminal as tests finish:]**
All two hundred and thirty tests pass cleanly in about twenty-five seconds."

---

### 4.2 Demo: Grounded Auto-Answer (8:00 – 9:30)
"Now, let’s test Case 1: a routine, answerable deployment failure. 

A customer submits a chat ticket saying: *'my deployment keeps dying at the container health check phase'*. Remember, the official article is titled *'Resolving container health check failures'*, so simple keyword search would fail to find it.

**[Type and run:]**
```powershell
python -m scripts.demo ticket "my deployment keeps dying at the container health check phase"
```

**[Point at output sections on screen as you explain:]**
Look at the terminal output:
* **Step 1 Classify:** Intent is classified as `deployment_failure` with 0.95 confidence.
* **Step 2 Retrieve:** The semantic search retrieved `DOC-DEPLOY-001#resolution` with a high similarity score of 0.81, well above our 0.40 threshold.
* **Step 3 Route:** Evaluated deterministic rule `answerable`.
* **Step 4 Generate & Validate:** The answer was drafted using prompt `PR-01`, citing the exact section. All guardrails passed.
* **Step 6 Act:** An automated reply was dispatched.

Look at the reply the customer receives: it gives the exact troubleshooting steps from the article, includes the mandatory automation disclosure, and provides the direct document link. The entire triage and resolution took less than a second. That is what I mean by grounded."

---

### 4.3 Demo: Safe Escalation of Protected Intent (9:30 – 10:45)
"Now, let’s test Case 2: a protected compliance request. 

The customer sends an email saying: *'Our auditor requires access logs for the last six months for our annual review.'*

**[Type and run:]**
```powershell
python -m scripts.demo ticket "Our auditor requires access logs for the last six months" --subject "Audit request" --channel email
```

**[Point at output on screen:]**
Notice what happened:
* The classifier identified `compliance_request` at 0.95 confidence.
* Even though we have a help article on access logs (`DOC-SEC-003`), our deterministic routing rule immediately fired: **`protected_intent`**.
* No automated draft was generated. Zero LLM tokens were spent trying to answer a legal compliance query.

Now look at what Daniel at tier two receives: a complete **Context Packet**. It includes the customer's tier, predicted intent, urgency, the exact reason for escalation, and the relevant help articles already pre-attached. Daniel doesn’t have to ask the customer to repeat themselves. He opens the ticket and has full context ready."

---

### 4.4 Demo: Active Guardrail Firewall Blocking (10:45 – 12:15)
"Now let’s look at the safety guardrails. Marcus’s number one rule was: *'Say nothing rather than say something wrong.'*

If an adversarial customer attempts prompt injection or asks for money, or if a model hallucinates, the guardrails must intercept the draft before it can ever leave CloudServe.

Let's run our dedicated guardrail test suite, which passes real candidate drafts through the active guardrail engine.

**[Type and run:]**
```powershell
python -m scripts.demo guardrail
```

**[Point at each blocked draft on screen:]**
Look at these four real scenarios:
1. **Draft 1:** A draft containing a refund promise (*'a refund has been issued to your card'*). **BLOCKED** by `forbidden_claims` for `refund_or_credit` and `fixed_on_our_side`.
2. **Draft 2:** A draft leaking an internal email address (`jane.doe@cloudserve.example`). **BLOCKED** by `pii`.
3. **Draft 3:** A draft inventing a citation to an article that was never retrieved (`DOC-PERF-002`). **BLOCKED** by `grounding`.
4. **Draft 4:** A draft promising a delivery date (*'fix will be deployed within 2 days'*). **BLOCKED** by `forbidden_claims`.

A blocked draft is never sent. The draft is suppressed, the ticket is safely escalated to staff, and the failed check is recorded in the audit log."

---

### 4.5 Demo: Full Unattended Harness Run & Audit Log (12:15 – 14:00)
"Now, let’s run the complete, unattended evaluation harness over the validation dataset. This is the exact command an external evaluator would run to grade the system.

**[Type and run:]**
```powershell
python -m evaluation.harness --input data/validation_tickets.json --output evaluation/results/demo_run
```

**[While it runs across the 80 tickets, speak calmly:]**
The harness reads the file, processes every ticket sequentially, handles edge cases gracefully, and writes an evaluation report. If a single ticket experiences a network timeout or provider glitch, the pipeline catches it, logs an emergency escalation, and continues without crashing.

**[As it finishes and outputs metrics:]**
Eighty tickets processed with zero unhandled exceptions.

Now, let's verify the audit trail for our first demo ticket.

**[Type and run:]**
```powershell
python -m scripts.demo log DEMO-01
```

**[Point at SQLite rows:]**
Here is the audit log stored in SQLite. For this ticket, there is an explicit row for classification, Chroma retrieval, routing, and guardrail validation. Every action is timestamped and mapped to its PRD requirement."

---

# SECTION 5: WHAT THE NUMBERS SAY (14:00 – 17:00)
**[Camera: Switch to Screen Share. Open `evaluation/results/validation/metrics.md`.]**

"Let’s examine the final validation results, evaluated over eighty unseen validation tickets.

**[Point at Business Outcomes Table]**
* **First-Contact Resolution:** On this set, historical human agents resolved 46.2% of tickets without escalation. Our system resolved **77.5%** without escalating—comfortably beating the client brief’s 60% target by 17.5 percentage points.
* **Escalation Rate:** Escalations dropped from 53.8% historically to **22.5%**, well within our 30% ceiling.
* **Response Latency:** For automated replies, median response time dropped from 218 minutes historically to **0.88 seconds**.

**[Point at Safety Section]**
* On safety: Fourteen tickets in the validation set were protected intents. **Zero protected tickets received an automated reply.** Every single one was escalated to human staff.

**[Point at Technical Performance]**
* **Triage Latency:** Triage alone—classifying, vector searching, and deterministic routing—runs in a median of 45.7 milliseconds, with a 95th percentile under 58 milliseconds.
* **Classifier Accuracy:** Intent macro precision was 100.0%.
* **Probability Calibration:** The stated intent confidence was within 2.1 points of actual accuracy, beating our 5-point constraint.
* **Retrieval Hit Rate:** The expected help article appeared in the top-5 retrieved passages in 96.2% of answerable tickets.
* **Citation Accuracy:** In our double-blind human review of 50 sampled replies with peer reviewer Sehil E, citation accuracy reached **96.0%** and hallucination was held to **4.0%**, with substantial inter-rater agreement at Cohen's kappa 0.79.

**[Face the camera or speak directly with authentic student voice:]**
For Marcus, these numbers mean his team can finally take a breath. Shifting three-quarters of the repetitive documentation questions away from his six agents means they aren't constantly burning out or playing catch-up. 

**However, we must be completely honest about what these numbers do not prove.** 
An offline validation run showing 'answered without escalating' does not prove the customer was completely satisfied. In historical static data, we cannot observe whether a customer had subtle follow-up questions. Furthermore, eighty tickets is a small validation set, and live production traffic will bring novel wording. That is why a 30-day shadow pilot is essential before full cutover."

---

# SECTION 6: FAIRNESS AND FAILURE TESTING (17:00 – 18:00)
**[Camera: Screen Share. Scroll to Fairness and Failure sections in `metrics.md` or Report.]**

"Let's look at two critical governance checks.

First, **demographic fairness**. I audited system performance across customer tier, region, channel, and language fluency. 
On development data, non-fluent English tickets had a retrieval hit rate about 7.4 points lower (87.4% vs 94.8%), because non-fluent customers often describe cloud issues without standard technical jargon. 

Crucially, our system handled this safely: rather than guessing, it fell below the 0.40 relevance floor and escalated non-fluent tickets to human agents at a higher rate (25.8% vs 20.6%). On validation data, that gap was eliminated, but because the non-fluent sample is small, I treat this as encouraging rather than definitively proven.

Second, **failure-injection testing**. In `tests/test_failure_injection.py`, I simulated twenty-five distinct catastrophic failure modes—including invalid API keys, HTTP 429 rate limits, network timeouts, empty ticket payloads, and missing vector databases. 

In every single failure case, the system never crashed. It caught the exception, generated a structured fallback escalation packet for human staff, and reconciled the audit log with 100% completeness."

---

# SECTION 7: WHAT I GOT WRONG, AND CLOSING (18:00 – 20:00)
**[Camera: Full Webcam. Look directly into the camera. Speak with humility, authority, and conviction.]**

"Finally, I want to discuss what I got wrong in Version 1.0 of my requirements, and what the empirical build taught me.

**First, I assumed a vector retrieval relevance score could distinguish answerable tickets from out-of-scope tickets.** It couldn't. A customer asking for a custom enterprise compliance audit shares extensive vocabulary with our security articles, scoring above 0.42. Similarity measures topical overlap, not whether the article actually answers the question. That’s why escalation had to be driven by deterministic intent rules, not retrieval scores.

**Second, I assumed customer urgency could be predicted reliably from ticket text.** It couldn’t. When I audited duplicate tickets in the development data, I found that **254 tickets shared identical wording across 97 groups, and in 67 of those groups—totaling 186 tickets—human agents had assigned conflicting urgency labels to the exact same text.** Machine learning cannot learn clean patterns from noisy human labels. Text-based urgency accuracy capped at 52%. So in PRD Version 2.0, I decoupled urgency from auto-response gating and reserved it strictly for post-escalation queue sorting.

**Third, I assumed standard sigmoid probability calibration would work.** It failed, leaving a 30.5-point gap between confidence and accuracy. Switching to multinomial logistic regression with Platt scaling closed that gap to 2.1 points.

**[Closing Reflection - Speak from the heart:]**
If this capstone project taught me one thing as an engineer, it's that the hardest part of building AI systems isn't tuning models or writing prompts—it’s understanding the operational reality of the people using them. 

CloudServe thought they needed an unconstrained conversational chatbot. But the data proved that what they actually needed was disciplined, boring, deterministic engineering: reliable retrieval, strict safety boundaries, and explainable human escalation.

Thank you very much."
