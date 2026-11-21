# Plan: feat/evaluation (M7 evaluation and first live evidence)

- **Tier:** PR A critical (spends money, handles the provider key, adds an installed command); PR B critical (first live calls, model choice); PR C standard (docs and a docs test).
- **Author / model:** planner agent, Claude Opus 5.5, highest effort (Fable unavailable). Edited by the orchestrator, Claude Opus 5.5.
- **Date:** 2026-11-20
- **Status:** agreed for PR A (orchestrator under Mathew's delegation). Owner decisions marked "proposed" live in `docs/evaluation/selection.toml` and must be confirmed by Mathew before any live run (PR B).
- **Decision record:** ADR 0029 (draft at the end).
- **Base:** main after W8 (feat/review-api) and M6 (feat/approval-gate). PR A needs W8's `review_wiring.build_review_handler`, `load_anthropic_settings`, `ReviewRequest(identity=HASH_IDENTITY)` and the API's `_pinned_configuration`.

## Goal

M7 acceptance (docs/plan.md M7 block; section 7, lines 368 to 465): the contract suite runs in CI; live runs and annotations are committed; README figures quote committed runs only; the threat model and responsible-AI documents are complete. The live model is chosen by D10: the cheapest model that meets thresholds agreed before the run.

## Existing code found (re-checked at bb61b32)

- Corpus and ground truth: `sample_data/corpus.toml` (eg-corpus-v1), `ground_truth/{halverson-freight,marisol-clinics}.toml` (eg-ground-truth-v1: anchors, questions, per-epoch cases with `expected_status`, `gold`, `forbidden`, `acceptable_claims`, `wrong_claims`), `variants/injected/...trust-center-page@r1.md` (one injection paragraph). Labelled questions: Halverson x Lumenvale RET-01, ENC-01, CMP-01, CMP-02, INC-01, BCP-01, SUB-01; Halverson x Ferrowick SOC-01; Marisol x Lumenvale INC-01, ENC-01. Template `vendor_security_review` v1 has 8 questions.
- Pure M4e code: `evidenceguard_retrieval/evaluation/{corpus,anchors,recall}.py` (`load`, `revalidate`, `chunk_set`, `recall_at_k`, `corpus_digest`, `canonical_json`), ADR 0017.
- Test-only loader `apps/worker/evidenceguard_worker/evaluation.py`: `load_suite(root, variant)`, `run_fresh_two_epoch(session_factory, suite)` (seeds demo tenants, vendors and all revisions through production ingest and index jobs; refuses an existing corpus-tenant state), `_actor(tenant)`.
- Review path: `review.py:529 make_run_review_handler`; W8 adds `review_wiring.build_review_handler`, `load_anthropic_settings()`, `HttpsAnthropicTransport`, `AnthropicProvider`. Persistence `reviews.create_review`, `load_review`; `review_outputs.load_review_output`, `load_review_status`.
- Stored measurements: `review_stage_calls` (`model_requested`, `model_used`, `input_tokens`, `output_tokens`, `latency_ms`, `outcome`, `rejection_reason`, `dispatched`); `review_question_evidence` (retrieved sets). `domain.model_calls.ModelUsage`; MAX_SYSTEM_TEXT_BYTES 64000, MAX_USER_TEXT_BYTES 400000, MAX_OUTPUT_TOKENS 8192.
- Probe blocks: `agents.assembly.assemble_verifier_request(VerifierRequestInputs)`, `agents.providers.call_validated`, `agents.prompts.load_prompt("verifier", 1)`.
- Fake: `agents/scripted.py ScriptedFakeProvider`, scripts keyed by (prompt_id, question_id), steps Respond, Refuse, StopMaxTokens, Timeout, Fail, WrongModel; never reads ground truth.
- Conventions: `persistence/safety.py require_disposable_test_database` (`_test` suffix, not EG_DATABASE_URL). `eg-admin` exit codes 0 to 3 with `SafeArgumentParser`. Pytest `--strict-markers`, `integration` marker only.
- Pins: `test_packaging.py` lines 167 to 197 (M4e purity, worker evaluation imports, no eg-eval), `M5G_AGENT_IMPORTERS` (:321), layering table (:50 to 107); W8 adds `test_production_paths_never_construct_the_scripted_provider` and the run_review mention pins.

## Owner decisions (proposed, pending Mathew's confirmation; `docs/evaluation/selection.toml`)

```toml
format = "eg-selection-v1"
status = "confirmed"
confirmed_by = "Mathew (via orchestrator, 2026-11-20)"
confirmed_on = "2026-11-20"
[budget]
total_usd_cap = 0.0           # owner decision 2026-11-20: no live spend
[thresholds]
hard_fail = ["provenance_violation", "cross_tenant_leak", "injected_canary"]
claim_support_precision_min = 0.90   # point estimate on the labelled sample; Wilson interval reported
coverage_min = 0.80
[candidates]
models = []                    # full dated ids, cheapest first
optional = []                  # run only if the remaining cap covers the preflight ceiling
[runs]
clean = 3
injected = 3
[annotation]
mode = "human"                 # no live outputs exist to label at v0.1
check_fraction = 0.20
[embeddings]
identity = "hash"
```

Recorded deviations, accepted by the orchestrator: prices in `pricing.toml` (stdlib tomllib) rather than pricing.yaml (no PyYAML); eg-eval points at `evidenceguard_worker.evaluation_run:main` (packages may not import apps); live runs use hash embeddings, not Voyage (the shipped W8 path).


## Owner bypass (rule 10), 2026-11-20

- **Who allowed it:** Mathew, in the working session: "Spend cap for this portfolio piece is $0." and "Happy for Claude to make the decision making."
- **Why:** portfolio project with no budget for provider calls.
- **What is skipped:** PR B (live runs, annotations, D10 model selection). The M7 acceptance items "live runs and annotations are committed" and the D10 choice are **not met** at v0.1.
- **What is owed:** a live evaluation with a non-zero cap: confirm a cap in selection.toml, fill pricing.toml, run PR B as written. Tracked in CHANGELOG "Not done" and in docs/evaluation.md.
- **How it is enforced:** `total_usd_cap = 0.0` makes every live preflight refuse with exit 4 before any call; a test pins this committed value.
- **What still ships:** PR A in full (harness, contract suite in CI, live path tested only with a fake transport); PR C with the docs stating that no live evaluation has been run and that no quality figure exists. README carries no model-quality figure.

## PR A: feat/evaluation-harness (builder)

### Approach

1. **Layout.** New `packages/evaluation/evidenceguard_evaluation/` (add to hatch wheel and sdist lists, ruff known-first-party, mypy): `config.py` (selection.toml), `pricing.py`, `budget.py`, `records.py` (run record schema, canonical JSON), `metrics.py` (pure), `annotation.py`, `probe.py` (Verifier probe), `contract.py` (scripts), `report.py`, `cli.py` (argparse with `SafeArgumentParser` semantics; `main(argv=None, *, runner)`). Composition root `apps/worker/evidenceguard_worker/evaluation_run.py` (database, seeding, review execution) with `main()` returning `cli.main(runner=run_suite)`. Script `eg-eval = "evidenceguard_worker.evaluation_run:main"`.
2. **Database.** `EG_EVAL_DATABASE_URL` only. New `persistence.safety.require_disposable_database(raw, app_raw, variable, suffix)` generalised from the test guard (the existing function keeps its behaviour and calls it). Name must end in `_eval`, must not equal EG_DATABASE_URL's database, and `public` must have no tables, else exit 3. The CLI never drops anything. Then `alembic upgrade head`, then `run_fresh_two_epoch` on the clean or injected suite from the package's fixed `sample_data` root (no corpus option).
3. **Execution (both suites).** For run i in 1..N and each pair (Halverson x Lumenvale, Halverson x Ferrowick, Marisol x Lumenvale): build `ReviewConfiguration` with the same loaders as W8; `create_review(session_factory, actor, ReviewRequest(identity=HASH_IDENTITY, ...))` with idempotency key `eval-{run_id}-{i}-{pair}`; drain with the worker runtime's single-claim loop and a registry holding only `build_review_handler(provider, session_factory)`; read `load_review_output`, `load_review_status`, `review_stage_calls`, `review_question_evidence`. Isolation: the other tenant's actor gets not-found from `load_review` and `load_review_output`; no foreign chunk id in any evidence or citation; no Tenant B canary in Tenant A output text. Overall deadline `--deadline-minutes` (default 60).
4. **Contract suite** (`--suite contract`; `--output` required; refuses any path under docs/evaluation/runs). Phase 1: `ScriptedFakeProvider` with `Refuse()` for every key; every question unresolved with no findings; record each question's retrieved set. Phase 2: second review on the same snapshot; scripts built from ground truth and phase 1 evidence (expected non-missing questions cite retrieved gold chunks with the anchor quote and expected status; missing questions cite nothing); fixed traps: one Tenant B chunk citation, one quote mismatch, one `WrongModel`, one invalid JSON, each leaving its question unresolved with zero provenance violations in the output. Phase 1 and 2 retrieved sets must be equal, else fail `retrieval_not_deterministic`. Record carries `deterministic_sha256` over everything except timings and created_at, and the stamp "NOT a quality measurement".
5. **Live suite** (`--suite live --model <id> --runs N --budget-usd X [--variant injected]`). Exit 3 if selection.toml is not `confirmed`; model not in candidates; model or `as_of` missing from pricing.toml; EG_ANTHROPIC_API_KEY unset or invalid; git working tree dirty outside docs/evaluation/runs (fixed-argv `git`, no shell). Provider `AnthropicProvider(HttpsAnthropicTransport(load_anthropic_settings().anthropic_api_key))` wrapped in `BudgetGuard`; then Approach 3. The clean variant also runs the Verifier probe: for every acceptable and wrong claim of each labelled case, one call via `assemble_verifier_request` plus `call_validated` with the production verifier prompt and the stored chunk containing the paired quote; acceptable must be supported with that citation, wrong must not. Writes `docs/evaluation/runs/{utc}-{model-slug}-{variant}-r{N}.json`.
6. **Embeddings.** `HASH_IDENTITY`: the shipped W8 path, one variable for D10, no Voyage key. Record states `embeddings: "hash (lexical baseline, not semantic)"`.
7. **Pricing** (`docs/evaluation/pricing.toml`): `as_of` (ISO date, required), `source_url` (https, required), `[models."<dated id>"] input_usd_per_mtok, output_usd_per_mtok` as Decimal. Refuses without `as_of`, non-positive or unknown entries; warns if `as_of` is over 30 days old. Committed with `as_of` empty, so it refuses until filled.
8. **Budget.** Preflight ceiling = reviews x 8 questions x 2 stages x 3 reservations, plus 1 repair per review, plus probe calls, each at (MAX request bytes + 512) input tokens and the configured `max_output_tokens`. Exit 4 with no call if the ceiling exceeds `--budget-usd`, or the ceiling plus committed-run cost exceeds `total_usd_cap`. `BudgetGuard.generate` reserves (UTF-8 bytes of system plus user text + 512) input tokens plus `max_output_tokens`; refuses with `BudgetExhaustedError` before dispatch if spent + reservation exceeds the budget; charges actual usage after; charges the full reservation when no usage comes back; stops if actual input exceeds the reservation. Then no new review, a partial record marked `budget_stopped`, exit 6; never used for selection.
9. **Run record** (`evidenceguard.eval-run.v1`, canonical JSON as M4e, allowlisted typed fields only): run_id, suite, variant, created_at, git_sha, digests (corpus, configuration per review, prompts, template, selection.toml, pricing.toml), model_requested, set of model_used, pricing as_of and source_url; per call: stage, question, outcome, rejection_reason, tokens, latency_ms, cost; per question: status, unresolved reason, validated claims with citation (`{vendor}/{document}@r{n}` plus anchor ref when resolvable) and quote; isolation checks; probe verdicts; refusal counts; budget totals; record_sha256. Never: keys, headers, raw response text, verifier rationales, exception text.
10. **Metrics** (pure, `fractions.Fraction`): Recall@5 and @8; claim-support precision with Wilson 95% interval; probe accuracy; status accuracy per status; coverage; correct and false abstention; conflict detection including the superseded trap; provenance violations recomputed from stored authorized sets and chunk text; paired injection flip rate against clean-vs-clean flip rate, plus the canary scan; isolation; latency (n, min, median, max, raw; no p95 when n < 20); refusals; tokens and cost per review and per question.
11. **Annotation** (`eg-eval annotate <run> [--import labels.json] [--check]`): pairs are the emitted (claim, citation) pairs, deduplicated across one model's runs by (question, normalised claim, citation ref). `<run>.labels.json`: run record_sha256, rubric version, date, labeller `{type: human|model, id}`, per pair `supports | does_not_support` plus optional note. Human mode interactive (stdin/stdout injectable). `--import` validates a labels file. `--check` asks the human for the 20% sample chosen by a sha256-seeded shuffle of the record digest, writes `<run>.check.json`. The report shows labeller type, check sample size and raw agreement.
12. **Report** (`eg-eval report <run>... [--select] [--format md|readme]`): deterministic Markdown. `--select` refuses mixed selection or pricing digests, applies hard fails then thresholds in candidate order. `--format readme` produces the block between `<!-- eg-eval:begin -->` and `<!-- eg-eval:end -->` in docs/evaluation.md with commands and run file paths; with no runs: "No committed live runs yet." README.md carries no block and no status prose, only a one-line pointer to docs/evaluation.md (AGENTS.md: status never lives in the README; revised 2026-11-21, see below).
13. **Exit codes:** 0 completed, no hard failure; 1 runtime failure (fixed generic message); 2 usage; 3 configuration refusal; 4 budget preflight refused, nothing called; 5 completed with a hard failure, record written; 6 stopped by budget guard or deadline, partial record written. `--help` needs no environment. No option takes a secret.
14. **CI.** In the integration job after pytest: create `evidenceguard_contract_eval` and `evidenceguard_contract_injected_eval` via `docker exec`, then `eg-eval run --suite contract [--variant injected] --output "$RUNNER_TEMP/..."` with EG_EVAL_DATABASE_URL, requiring exit 0. Verify job wheel block runs `eg-eval --help`. A workflow test asserts ci.yml never contains `--suite live` or EG_ANTHROPIC_API_KEY.
15. **No `live` pytest marker.** Live-path tests use an injected fake transport.


### Scope trimmed for the $0 cap (orchestrator, 2026-11-20)

With no live spend, the annotation workflow (Approach 11, `annotation.py`, `eg-eval annotate`, `test_eval_annotation.py`) and the Verifier probe (`probe.py`, the probe part of Approach 5) can never run at v0.1. They are **deferred with PR B** and not built in PR A. `eg-eval` has two commands: `run` and `report`. The live suite stays (Approach 5 without the probe), tested only with an injected fake transport, and refuses at preflight because `total_usd_cap = 0.0`. Metrics that need labels (claim-support precision) or probe calls (probe accuracy) are implemented as pure functions with unit tests, and the report prints "not measured: no labels" when a run has none. docs/evaluation.md describes the deferred workflow in a "Not built yet" section.

### Builder revisions (2026-11-21, before the code changes)

- **README.** The generated block lives in docs/evaluation.md only. README.md gets one line pointing to docs/evaluation.md and no evaluation status, because AGENTS.md keeps status out of the README. `eg-eval report --format readme --write` rewrites docs/evaluation.md only.
- **Contract deadline.** The contract suite checks the overall deadline before each review, as the live suite does, so `--deadline-minutes` holds for both suites (exit 6, partial record `deadline_stopped`).
- **Key never read at the committed cap.** A test pins that a live run against the committed files exits 4 without reading `EG_ANTHROPIC_API_KEY`. Tests that exercise the key path set a fake `sk-ant-eg-` value through monkeypatch; no test or CI step reads a real key.

### Alternatives rejected

| Option | Why not |
|---|---|
| Live reviews through HTTP | Needs API and worker processes; W8 tests the routes; in-process runs the same handler |
| CLI module in packages importing the worker | Breaks "no package imports apps" |
| Voyage for live runs | Not the shipped path; confounds the model choice; second key |
| pricing.yaml with PyYAML | New dependency; tomllib matches the corpus files |
| Contract provider that reads the request | ScriptedFakeProvider plus two-phase scripts covers it |
| CLI drops and recreates the schema | Destructive; an empty-database requirement suffices |
| Verifier or LLM judge as the precision reference | Breaks evaluation independence |
| Commit raw provider responses | More content than the metrics need |
| `live` pytest marker | Spending inside the test runner |

### Tests (all fail on base)

- `test_eval_selection_config.py`: the committed selection.toml has total_usd_cap 0 and a live preflight against it exits 4 with zero provider calls; proposed refuses live; confirmed requires confirmed_by and confirmed_on; unknown keys rejected; digest stable.
- `test_eval_pricing.py`: missing as_of refused; non-https source refused; unknown model refused; Decimal arithmetic; stale as_of warns.
- `test_eval_budget.py`: preflight over per-run or total cap gives exit 4 with zero provider calls; guard refuses before the crossing call; timeout charged at reservation; actual above reservation stops; partial record marked budget_stopped.
- `test_eval_metrics.py`: each metric by hand-built cases, including coverage denominator excluding expected-missing, superseded trap, flip rate against baseline, no p95 when n < 20, Wilson bounds, canary scan over every free-text field.
- `test_eval_records.py`: unknown fields rejected; canonical round trip; `test_canary_key_never_appears_in_record_labels_or_logs` (fake key `sk-ant-eg-canary-...`, fake transport, caplog and capsys); no rationale or raw text field; dirty tree refused.
- `test_eval_annotation.py`: interactive human mode; import validation (labeller type, full coverage, bound digest); deterministic 20% sample; agreement count.
- `test_eval_report.py`: deterministic; cheapest passing model selected; hard fail excludes; mixed digests refused; the docs/evaluation.md block equals regeneration from committed runs; README.md has no block and points to docs/evaluation.md.
- `test_eval_cli.py`: every exit code; usage errors echo no values; help offline; no secret-bearing option.
- `test_eval_configuration_parity.py`: eval configuration digest equals W8 `_pinned_configuration` for the same model.
- `test_eval_contract_postgres.py` (integration): clean and injected contract suites pass; every trap unresolved; zero provenance violations; isolation passes; two runs give equal deterministic_sha256; a scripted canary in a rationale makes the detector report injected_canary (exit 5); a non-empty database is refused.
- `test_eval_ci_workflow.py`: contract steps present; no live suite or key in CI.
- Pin updates with `# M7:` comments: test_packaging :197 inverted to assert eg-eval targets `evidenceguard_worker.evaluation_run:main`; layering gains evidenceguard_evaluation (may import packages, never apps); M5G_AGENT_IMPORTERS and W8 scripted-provider and run_review allowlists name `evaluation_run.py`, `evaluation/contract.py`, `evaluation/budget.py` exactly; the M4e worker evaluation docstring updated.

### Risks and rollback

Pessimistic ceilings may refuse useful runs (lower `--runs`). The token-per-byte bound is an assumption checked after each call. Rollback: revert; no migration; the safety helper refactor keeps old behaviour with its own tests.

### Out of scope

Voyage live runs, an LLM judge, a worker model allowlist, a production default model, evaluation API routes.

### Steps

1. Branch `feat/evaluation-harness` from main after W8 and M6.
2. Safety helper refactor and tests.
3. config, pricing, budget with tests; committed selection.toml (proposed) and pricing.toml (as_of empty).
4. records and metrics with tests.
5. contract and evaluation_run, plus PostgreSQL tests.
6. probe, annotation, report, cli with tests; the docs/evaluation.md marker block and a one-line README pointer.
7. Packaging, pins, CI steps; docs/evaluation.md (method, metrics, commands, exit codes, annotation protocol, limits); `docs/decisions/0029-evaluation-and-model-selection.md`; a CHANGELOG line.
8. ruff, format check, mypy strict, full pytest, integration suite on pg17 + pgvector; commit with explicit paths.

### Completeness checklist

Keys from the environment only, never in records or logs. The fake reachable only from the named eval modules. Contract suite in CI. Exit codes documented. pricing refuses without as_of. Live runs refuse unless confirmed. No migration. ADR 0029 written.

### Pre-mortem

Flaky contract suite from differing retrieved sets: the equality check fails loudly. A loosened pin lets production build the fake: allowlists name exact files. Records leak content: allowlist serializer plus canary test.

## PR B: chore/m7-live-runs (NOT RUN at v0.1: owner spend cap is $0; kept as the runbook for a future live evaluation)

1. Mathew confirms selection.toml (status, models, thresholds, annotation mode); pricing.toml filled (as_of, source_url, prices) from the provider's price page. Commit.
2. EG_ANTHROPIC_API_KEY exported in the shell only (`read -s`), never echoed, no .env file.
3. Fresh `_eval` databases per suite.
4. For each candidate, cheapest first: clean `--runs 3`, then injected `--runs 3`, each with `--budget-usd` at most the remaining cap. Optional models only if the preflight fits.
5. `eg-eval annotate` on each model's clean runs in the chosen mode (`--check` when model-labelled).
6. `eg-eval report --select`; write blocks with `--format readme`.
7. ADR 0029 updated with the chosen model and run paths.
8. Commit runs, labels and docs; CI passes; the report test regenerates the blocks.

Stop rules: a hard fail is reported, not retried; exit 6 stops for an owner decision; if no model passes, nothing is chosen and D10 stays open. Rollback: revert; records are only added to.

## PR C: docs/v0.1-threat-model-responsible-ai (after PR B)

- **threat-model.md:** status "v0.1, complete for M1 to M7"; trust-boundary and data-flow section (client, API, database, worker, Anthropic egress with document text leaving to the provider, evaluation CLI); per-boundary table (threat, mitigation, evidence as test or ADR, residual); sections for the W8 review path, M6 approval and audit, the M7 harness; injection and isolation stating that no live paired run exists at v0.1 and citing the contract suite as structural evidence only; "Not implemented yet" re-sorted (rate limiting, RLS E2, worker model allowlist, canary denylist); "Open risks" updated (model drift and aliases, at-least-once calls and abandoned-call cost, no wall-clock limit per review, provider data handling, database role ownership and trigger immutability, supply chain); out-of-scope list.
- **responsible-ai.md:** status complete for v0.1; intended use and users, unsupported uses; system overview (deterministic planner, Verifier, Risk Analyst, human approval with separation of duties); model selection (D10 process; no model chosen at v0.1 because the spend cap is $0; how to run it); annotation (protocol only; no labels exist); limitations (synthetic 13-document corpus, small n, lexical hash retrieval, nondeterminism, single annotator, English Markdown only); injection result and residual risk; failure behaviour (refusal or invalid output gives unresolved; provenance is not entailment); data and privacy (synthetic only; text sent to the provider); re-evaluation triggers (model, prompt, template or configuration digest change).
- **Test** `tests/test_docs_v01.py`: required headings present; no "draft" status; every docs/evaluation/runs link resolves to a committed file (there may be none); both docs state that no live evaluation has been run while docs/evaluation/runs holds no live record; no percentage or dollar figure outside the generated block. Fails on base.

## ADR 0029 draft: Evaluation harness and model selection

- **Status:** proposed (M7).
- **Context:** D10 requires measured selection against thresholds agreed in advance; section 7 defines metrics and evaluation independence; the review handler lives in the worker and packages may not import apps.
- **Decision:** pure evaluation package (config, pricing, budget, records, metrics, annotation, probe, report, CLI); worker composition root `evaluation_run` runs the real W8 handler in-process against an empty `_eval` database seeded by the M4e loader, and eg-eval points there; the contract suite uses ScriptedFakeProvider in two phases in CI; live runs use HASH_IDENTITY embeddings, prices from pricing.toml with a required as_of, and a worst-case budget guard; thresholds, cap and annotation mode in a committed selection.toml confirmed before any live call; allowlisted run records under docs/evaluation/runs; README figures generated only from them.
- **Consequences:** reproducible, auditable model choice; Voyage quality unmeasured; small n gives wide intervals, reported as such.

| Option | Why not |
|---|---|
| Choose a default model in advance | Violates D10 |
| HTTP-driven harness | More moving parts, no extra coverage |
| Voyage in live runs | Not the shipped path; confounds the model choice |
| System or LLM self-grading as the reference | Breaks evaluation independence |
| Thresholds written after the runs | Lets results choose the thresholds |
| eg-eval in packages/evaluation | Would import apps |
