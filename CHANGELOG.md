# Changelog

Short record of merged changes, newest first. Details live in each pull request.

## Unreleased

- M7 PR A (ADR-0029): `eg-eval` evaluation harness with the contract suite in CI (scripted
  fake, NOT a quality measurement), a budget-guarded live suite and deterministic reports.
  **Not done:** no live evaluation has been run and no model is chosen (D10 open): the owner's
  spend cap is $0, so `selection.toml` has `total_usd_cap = 0.0`; annotation and the Verifier
  probe are deferred with the live runs.
- M6: report approval gate and export under `/v1/reports` (hash-bound revisions, approve or
  reject, finalize, Markdown and JSON export, append-only history and audit; migration 0009,
  ADR-0028).
- W8 (ADR-0027): review API routes, production `run_review` registration and Anthropic provider configuration, off unless `EG_REVIEW_PROVIDER` and `EG_REVIEW_MODEL` are set; in-flight reviews per tenant capped by `EG_REVIEW_MAX_IN_FLIGHT` (default 2, 429 over the cap).
- Working agreement moved to `AGENTS.md`; every change now goes through a reviewed pull request.
