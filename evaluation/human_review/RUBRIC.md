# Human review: instructions for reviewers

You are checking automated replies that the system sent to customers. Work alone, and don't look
at the other reviewer's sheet until you have both finished.

Open your sheet (`reviewer_A.csv` or `reviewer_B.csv`) in Excel or Google Sheets. Each row has the
customer's ticket, the reply that was sent, and the full text of every help-article passage the
reply cites. Judge the reply **only against those passages**, not against what you know about
cloud platforms.

Fill in three columns for every row:

## 1. `unsupported_claim`: yes or no

**yes** if the reply states at least one fact, step or number that the cited passages do not
contain. Examples: a timeout value that isn't in the passage, a cause the passage doesn't mention,
a promise ("this will fix it"), or advice from general knowledge.

**no** if everything the reply says can be found in, or directly follows from, the cited passages.
Rewording is fine. Polite filler ("I hope this helps") is not a claim.

## 2. `citations_support`: all, some or none

Look at each citation and the sentence it is attached to.
- **all**: every citation points to a passage that supports its sentence.
- **some**: at least one citation does not support the sentence it is attached to.
- **none**: no citation supports its sentence.

If the reply lists sources but has no citations inside the text, judge whether the listed passages
support the reply as a whole.

## 3. `would_send`: yes or no

Would you, as a support agent, send this reply to the customer without changing it? Say **no**
if it is wrong, misleading, answers a different question, or is too vague to act on.

## `notes`

Optional. Quote the unsupported sentence, or say what is wrong. Notes make the disagreement
discussion much faster.

## When you have both finished

```bash
python -m evaluation.human_review.score_review --a evaluation/human_review/reviewer_A.csv --b evaluation/human_review/reviewer_B.csv
```

This writes `review_results.md` with the hallucination rate, citation accuracy, agreement between
reviewers and a list of disagreements. Discuss each disagreement and agree a final verdict. In the
report, state the sample size, who the two reviewers were, the agreement figures, and how the
disagreements were settled.
