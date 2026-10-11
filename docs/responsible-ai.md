# Responsible AI (initial draft, M1b)

**Status:** draft. This document must be complete before v0.1 ([plan](plan.md) correction F). No model is called by the code yet.

## Purpose and limits

EvidenceGuard is **decision support** for vendor-risk reviewers. It is not legal advice, and it does not certify compliance.

- A report organizes what the uploaded documents say, with citations, and flags conflicts and gaps for a human to judge.
- **Human approval does not establish that documents are authentic, and it does not certify the vendor as compliant.** It records that a named approver accepted one exact revision of the report's content.
- Every citation carries `authenticity: not_established`. A document labelled `third_party_report` is described as documentary support, never as independently verified.

## What the evidence labels mean

| Status | Meaning | What it does not mean |
|---|---|---|
| `vendor_claim` | Only the vendor's own statements support the answer. | That the claim is true. |
| `documentary_support` | At least one contract or third-party document supports it. | That the document is genuine or current beyond what it says. |
| `conflicting` | Current documents appear to disagree. At least two distinct quotations are cited; they may come from the same passage. | Which one is right, or that the quotations truly contradict each other. The quotation count is a structural check only. |
| `missing` | No sufficient evidence was found. Partial passages may still be cited. | That the vendor lacks the control. |

**No question is silently dropped.** Every question in a report is either answered by a finding or listed as unresolved:
- A `missing` finding leaves every question it names unresolved, even when other evidence partly supports that question.
- A vendor claim cannot settle a question that requires documentary support. It is still shown, and the question stays unresolved.

## Implemented and tested now (M1b)

- The status and citation rules above are enforced when results are built.
- A finding cannot claim support or conflict without citations.
- Reports can only be finalized and exported after an approver approves the exact current revision. Any edit after approval requires a new approval.
- A rejection must state its reason.
- Retried decisions never overwrite the record of who decided what: a changed retry is refused as a conflict.

## Pending

- **Semantic validation.** Citation checks will prove provenance (the quote exists in an authorized document), not that the passage supports the claim. Support will be judged by the model and measured against human labels (M5–M7).
- **Prompt-injection evaluation.** Planned with paired clean and injected document sets (M7). Defences will reduce, not remove, the risk.
- **Model refusals and invalid output** will leave questions unresolved rather than guessed (M5).
- **Evaluation independence.** Human labels are the reference standard; the system's own judgments are never counted as evaluation results (M7).
- **Data.** Only synthetic, fictional vendors and tenants are used. No real client or personal data belongs in this repository.
