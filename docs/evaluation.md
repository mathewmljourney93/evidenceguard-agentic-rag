# Evaluation

**Status at v0.1: no live evaluation has been run, and no model-quality figure exists.** The
owner set the spend cap for this portfolio project to $0 (2026-11-20), so the committed
`docs/evaluation/selection.toml` has `total_usd_cap = 0.0` and every live run refuses with exit
code 4 before anything is called. The contract suite runs in CI; it checks invariants with
scripted responses and is **NOT a quality measurement of Claude or semantic retrieval**. The
model choice of D10 is still open. Decision record: [ADR-0029](decisions/0029-evaluation-and-model-selection.md).

<!-- eg-eval:begin -->
No committed live runs yet.
<!-- eg-eval:end -->

## Method

`eg-eval` runs the production review handler in one process against an empty PostgreSQL
database whose name ends in `_eval` (`EG_EVAL_DATABASE_URL`; never the application database).
It applies the migrations, loads the synthetic corpus in `sample_data/` through the M4e loader
(both tenants, every revision, hash embeddings) and creates one review per (tenant, vendor) pair
with labelled questions: Halverson Freight with Lumenvale Cloud and with Ferrowick Payroll, and
Marisol Clinics with Lumenvale Cloud. Reviews pin the same template, prompts and settings as the
review API, use `HASH_IDENTITY` (a lexical baseline, not semantic) and are drained with the
worker's single-claim loop over a registry that holds only the production review handler. The
stored output, status, call rows and retrieved sets are then read back and scored against the
human ground truth of the `final` epoch.

### Contract suite (`--suite contract`, CI)

The scripted fake provider answers in two phases per pair:

1. **Refusal phase.** Every call refuses. Every question must end unresolved with no finding;
   each question's retrieved set is recorded.
2. **Scripted phase.** A second review of the same pair. Answers are built from the ground truth
   and the refusal phase's retrieved sets: expected non-missing questions cite the retrieved
   chunks containing the gold anchor quotes with the verdict that yields the expected status;
   expected-missing and unlabelled questions answer `insufficient_evidence`. Four fixed traps
   (on Ferrowick questions the ground truth leaves unlabelled) must each leave their question
   unresolved with no provenance violation: a citation of the other tenant's chunk, a quote not
   in the cited chunk, a response naming another model, and invalid JSON.

The run fails (exit 5) unless both phases' retrieved sets are equal, every trap is unresolved,
the refusal phase resolved nothing, there are zero provenance violations, isolation holds and no
injected-canary text appears in any output. The record carries `deterministic_sha256` over
everything except the run id, the creation time and latencies; two runs on the same tree give
the same value.

### Live suite (`--suite live`, by hand only; not run at v0.1)

Refusals happen in this order, before any database or provider exists:

1. the total cap minus committed run spend is zero, or `--budget-usd` is not positive: exit 4
   (the committed cap of 0 stops every live run here);
2. `selection.toml` not `confirmed`, the model not a candidate, `pricing.toml` without `as_of`,
   an https `source_url` or the model's prices, `EG_ANTHROPIC_API_KEY` unset or invalid, or a
   working tree with changes outside `docs/evaluation/runs`: exit 3;
3. the worst-case ceiling above `--budget-usd` or above the remaining total cap: exit 4.

The ceiling is reviews x (8 questions x 2 stages x 3 reservations + 1 repair) calls, each at
the maximum request size plus 512 input tokens and the configured `max_output_tokens`. Calls go
through `BudgetGuard`, which reserves each call's worst case before dispatch and refuses when the
budget would be crossed; a stop writes a partial record marked `budget_stopped` (exit 6), never
used for selection. Records go to `docs/evaluation/runs/{utc}-{model}-{variant}-r{N}.json`.

## Metrics

All exact ratios are `fractions.Fraction`, recorded as numerator and denominator.

| Metric | Definition |
|---|---|
| Recall@5, Recall@8 | Gold chunks among the first k retrieved, averaged over questions with gold |
| Claim-support precision | Human `supports` labels over all labelled (claim, citation) pairs, with a Wilson 95% interval; "not measured: no labels" without labels |
| Probe accuracy | Correct Verifier probe verdicts over all probe claims (probe not built yet) |
| Status accuracy | Output status equal to the expected status, per expected status |
| Coverage | Questions given a non-missing status, over questions not expected missing |
| Correct and false abstention | `missing` over expected-missing questions, and over the others |
| Conflict detection | `conflicting` over expected-conflicting questions; false conflicts; citations of superseded passages |
| Provenance violations | Citations outside the question's stored retrieved set or whose quote is not in the stored chunk text (hard failure) |
| Isolation | The other tenant gets not-found for the review and its output; no foreign chunk in evidence or citations; no other-tenant canary in the output (hard failure) |
| Injected canary | The injected paragraph, or its leading clause, in any free-text output field (hard failure) |
| Injection effect | Paired status flip rate between clean and injected runs against the clean-versus-clean flip rate |
| Latency | n, min, median, max and raw values; a p95 only when n >= 20 |
| Refusals, tokens, cost | Calls by outcome; usage; cost from `pricing.toml` per review and per question |

## Commands

```
eg-eval run --suite contract --output PATH [--variant injected]
eg-eval run --suite live --model ID --runs N --budget-usd X [--variant injected]
eg-eval report RUN... [--select] [--format md|readme] [--write]
```

`report --format readme --write` regenerates the marker block in this file from the given
committed live runs; a test checks that the block equals that regeneration. `README.md` holds no
block and no evaluation status, only a pointer to this file.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | completed, no hard failure |
| 1 | runtime failure (fixed generic message) |
| 2 | usage error (no value is echoed) |
| 3 | configuration refusal |
| 4 | budget preflight refused, nothing called |
| 5 | completed with a hard failure (or a contract failure), record written |
| 6 | stopped by the budget guard or the deadline, partial record written |

No option takes a secret; the key is read from `EG_ANTHROPIC_API_KEY` only. Records hold only
allowlisted typed fields: never a key, header, raw response text, Verifier rationale or
exception text.

## Not built yet

Deferred with the live runs (PR B), because they can never run under a $0 cap:

- **Annotation** (`eg-eval annotate`). Protocol: the emitted (claim, citation) pairs of one
  model's runs, deduplicated by question, normalised claim and citation, are labelled
  `supports` or `does_not_support` in `<run>.labels.json`, bound to the record's
  `record_sha256`, with the rubric version, the date and the labeller (`human` or `model`). With
  model labelling, a 20% sample chosen by a SHA-256-seeded shuffle is checked by a human and the
  raw agreement is reported.
- **Verifier probe.** For each acceptable and wrong claim of each labelled case, one production
  Verifier call with the stored chunk holding the paired quote; acceptable claims must be
  supported with that citation, wrong claims must not.

## What is owed

A live evaluation needs a non-zero cap confirmed in `selection.toml`, the candidate models,
`pricing.toml` filled from the provider's price page, and then the PR B runbook in
`docs/plans/feat-evaluation.md`: clean and injected runs per candidate, annotation, `report
--select`, and the generated blocks.

## Limits

Synthetic corpus of 13 documents; small n gives wide intervals; hash retrieval is lexical, not
semantic; model output is nondeterministic; one annotator; English Markdown only. The contract
suite proves wiring, isolation and provenance checks with scripted responses, not model quality
or injection resistance.
