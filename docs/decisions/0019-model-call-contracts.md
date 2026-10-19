# ADR-0019: Model-call contracts, the validating call boundary and the scripted fake

- **Status:** **Accepted at external review in Prompt 173 for the local implementation commit;
  published and verified in feature-branch CI at `9ba6a488` in Prompt 174; feature CI evidence
  accepted at external review in Prompt 176; on `main` at `f04e0957` (Prompt 176), verified in
  feature-branch and main-push CI for that exact commit** (see
  [Feature-branch CI evidence (Prompt 174)](#feature-branch-ci-evidence-prompt-174) and
  [Main publication evidence (Prompts 176–177)](#main-publication-evidence-prompts-176177)). The
  Prompt 176 documentation commit itself records the pre-publication state (M5a not merged, `main`
  at `46c02257`, publication authorized but not yet run); that wording is historical.
  Implemented in Prompt 171 and corrected in Prompt 172 (see
  [Prompt 172 corrections](#prompt-172-corrections) and
  [External review (Prompt 173)](#external-review-prompt-173)). Implements the
  [accepted M5a specification](../plan.md#m5a-model-call-contracts-and-scripted-fake-provider-accepted-at-review-prompt-170-implementation-pending)
  (proposed in Prompt 167, corrected in Prompt 168, clarified in Prompt 169, accepted at external
  review in Prompt 170 with W-A1 to W-A11 as its implementation contract), the first slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
- **Date:** 2026-10-19
- **Builds on:** [ADR-0003](0003-plain-python-workflow.md) (plain-Python workflow),
  [ADR-0016](0016-snapshot-retrieval.md) (the value and fixed-error style reused here) and
  [ADR-0018](0018-voyage-adapter.md) (the explicit-construction, mocked-provider precedent).

## Decision

M5a adds the values every later M5 slice uses to ask a model for a structured judgment and to
classify what came back, one shared validating call boundary, and a deterministic, test-owned
scripted provider. It is pure: no database, migration, network, credentials, settings, prompts,
provenance checks, orchestration, `JobContext` or handler registration, and no change to any
M1–M4 contract. Nothing constructs a provider in production.

## Modules

| Module | Contents | Imports |
|---|---|---|
| `evidenceguard_domain.model_calls` | `ModelPurpose`, `PromptRef`, `ModelUsage`, `StopKind`, `CallOutcome`, `StructuredRequest`, `ProviderResponse`, `StructuredResult`, bounds, the canonical request encoding and the fixed errors | standard library; `agent_outputs` locally (below) |
| `evidenceguard_domain.agent_outputs` | `QuoteRef`, `ClaimOutput`, `VerifierOutput`, `FindingOutput`, `AnalystOutput`, the closed schema registry and `parse_output` | standard library, Pydantic, `evidence`, `model_calls` |
| `evidenceguard_agents.providers` | `ModelProvider`, `ModelCallTimeout`, `call_validated` | standard library, domain |
| `evidenceguard_agents.scripted` | `ScriptedFakeProvider`, its steps and `CallRecord` | standard library, domain, `providers` |

`evidenceguard_agents` is a new import package (wheel, sdist and strict mypy). Packaging tests
forbid it from importing persistence, retrieval, the apps or SQLAlchemy; they forbid every other
package from importing it; and they restrict the M5a modules to the standard library and the domain
(plus Pydantic in `agent_outputs`) with no `socket`, `ssl`, `http`, `urllib`, `os`, `pathlib`,
`tomllib` or `io`. These are architectural checks against accidental access, not a sandbox against
malicious trusted Python code.

**Dependency arrangement.** `agent_outputs` imports `model_calls` at module level (for
`ModelPurpose`, the schema identifiers, `utf8_size` and `InvalidModelValueError`). `StructuredResult`
needs the output classes only to check an `output` value, so it imports `agent_outputs` **inside**
that check (`_check_output`). There is no cycle at module load, and `model_calls` stays importable
without Pydantic. `model_calls` repeats the `QuestionId` pattern rather than importing the
Pydantic-based `evidence` module; a test pins the two patterns as equal.

## Behaviour (as specified)

- **Call values** are frozen dataclasses with exact-type validation (no coercion, no `bool` for
  `int`), unknown keywords rejected, no stripping, derived fields (`output_schema`,
  `request_sha256`) computed by the constructor, and revalidation through `dataclasses.replace`.
  Nested `PromptRef` and `ModelUsage` values are rebuilt, so a bypassed nested value is caught.
- **`StructuredResult`** validates every field and accepts only the five rows of the accepted table:
  output only for `completed`; `model_used` and `usage` together, only for a received valid
  response (equal to the requested model except for `model_mismatch`); nothing for `timeout`;
  `provider_failed` with latency only when dispatched. A supplied output is revalidated.
- **Canonical encoding** `eg-model-call-canonical-v1`: sorted keys, compact separators, ASCII,
  `allow_nan=False`; texts enter only as SHA-256 of their UTF-8 bytes; `timeout_ms` is excluded.
  The digest is pinned in tests against independently computed bytes. It identifies request
  content for reuse and audit; it is not authorization or proof of a call or of any past state.
- **Output schemas** are strict, frozen, non-stripping Pydantic models with `extra="forbid"`,
  `revalidate_instances="always"` and `hide_input_in_errors=True`. Every collection is a tuple;
  attribute assignment and deletion raise `InvalidModelValueError`. Quote references use the
  canonical lowercase hyphenated UUID spelling (a pattern, so other spellings are rejected, never
  normalized) with a `chunk_uuid` property; exact duplicate quote references within one claim or
  finding and duplicate finding question IDs are rejected; text rejects NUL and lone surrogates.
- **Parsing** is two-pass: at most 65,536 UTF-8 bytes; a `json.loads` scan with a duplicate-key
  hook, non-finite constant and number rejection, a JSON-object top level and an iterative walk
  bounding depth to 8 and the value count to 2,000; then strict **JSON-mode** validation of the same
  text. Every failure gives `None` (`invalid_output`).
- **Validation-error privacy:** `__init__`, `model_validate`, `model_validate_json`,
  `model_validate_strings` and `model_copy` run each whole operation (input traversal, reading the
  update mapping, copying and validation) inside one boundary that turns any ordinary failure into
  a fresh `InvalidModelValueError` raised after the handler (no cause, context or original text),
  and accept no extra options (strictness cannot be switched off per call).
  `model_validate_strings` is the same strict Python-mode validation as `model_validate`
  (Prompt 172). `repr`, `str` and `__repr_args__` show the
  type name and counts only, for every nested type.
- **`call_validated`** follows the accepted order: revalidate the request (rebuilt and compared on
  `output_schema` and `request_sha256`) and require a callable clock, else
  `InvalidModelRequestError`; an unusable start reading raises `ModelClockError`; `provider_id`
  must be exactly a `str` matching `^[a-z][a-z0-9-]{0,31}$`, else `provider_failed` without
  dispatch; one `generate` call (`ModelCallTimeout` → `timeout`, any other ordinary exception →
  `provider_failed`); the end reading; response and nested usage revalidation (else
  `provider_failed` without accounting fields); then model mismatch, refusal, `max_tokens`, other
  stop and strict parsing, in that precedence. No retry, no repair. Only `Exception` is caught;
  process control from the clock, `provider_id` or `generate` propagates as the same object.
- **Clock:** a reading is usable only if it is exactly an `int` within ±2**53 (checked with integer
  comparisons before conversion, so `10**1000` never reaches `float` or `math.isfinite`) or exactly
  a finite `float` within the same bound. After dispatch, an unusable end reading, backwards time, a
  latency above 86,400,000 ms or any ordinary failure while calculating leaves `latency_ms` absent
  and keeps the outcome; a latency is never clamped or invented.
- **Scripted fake:** `Respond`, `Refuse`, `StopMaxTokens`, `StopOther`, `Timeout`, `Fail` and
  `WrongModel` steps keyed by `(prompt_id, question_id)`; at most 256 keys, 16 steps per key,
  65,536 bytes per text and 4 MiB of script text in total, copied into immutable tuples. Under one
  lock each call takes its key's next step and appends a `CallRecord` (identifiers, request digest
  and step index only; capped at 4,096); the step runs outside the lock. A missing key, an exhausted
  script (the last step is never repeated) or a full history raises the fixed `ScriptedFakeError`
  without recording. Reading the supplied configuration mapping is inside the same kind of error
  boundary (Prompt 172). Scripts hold raw text for a test-owned lifetime; representations show the
  model ID and counts only.

## Implementation choices and deviations (approved at review)

1. **Pydantic base-init flag.** To translate validation errors, the output base overrides
   `__init__`. Pydantic 2.14 treats any `__init__` that lacks the `__pydantic_base_init__` flag as a
   custom initializer and, during `model_validate_json`, calls it with the raw decoded values; strict
   Python-mode validation then rejected valid JSON enum strings (observed locally with the locked
   Pydantic 2.14.0 while implementing). The override only wraps `BaseModel.__init__`, so it carries
   the same flag Pydantic sets on its own `__init__`. This relies on a Pydantic source-level
   convention: `test_pydantic_treats_the_wrapping_init_as_its_own` pins
   `__pydantic_custom_init__ is False` for every output type, and the JSON-mode parsing tests fail
   if the convention changes.
2. **Nested-instance rule at the Python-mode entry points.** Strict Python mode accepts a `dict` for
   a nested model field (observed locally). The accepted contract requires nested model instances
   in direct construction, so `__init__`, `model_validate` and `model_validate_strings` reject a
   nested tuple field whose items are not exact instances. A schema-level `before` validator was
   tried first and rejected: in JSON mode it hands the decoded list to strict tuple validation as a
   Python value, which then fails. JSON-mode validation is therefore unaffected.
3. **`WrongModel` must name a different model.** The fake's constructor rejects a `WrongModel` step
   whose `model_used` equals the fake's own model ID, since such a step would not exercise a
   mismatch. This narrows the accepted step definition for fixtures only.
4. **The revalidated request is dispatched.** `call_validated` passes the rebuilt request (equal in
   every field and digest) to `generate`, not the caller's object.
5. **Ruff first-party list.** `pyproject.toml` also adds `evidenceguard_agents` to Ruff's
   `known-first-party`, alongside the other import packages, so imports sort correctly. It relaxes no
   rule; it is outside the literal "packaging and mypy lists" wording and is flagged for review.
6. **Model-validation options.** The public validators accept no keyword options (for example
   `strict=False` or `from_attributes=True` raise `InvalidModelValueError`), so strictness cannot be
   weakened per call.

## Verification (Prompt 171, local Windows, Claude Code; historical)

All in the existing locked environment (`uv … --locked --offline`; no dependency or lockfile
change), on Windows only; Linux and CI have not run.

- `ruff check .` and `ruff format --check .`: clean (186 files). Strict `mypy`: no issues in 148
  source files, including `evidenceguard_agents`.
- Focused (six-file command): `tests/test_model_calls.py`, `tests/test_agent_outputs.py`,
  `tests/test_scripted_provider.py`, `tests/test_packaging.py`, `tests/test_evidence.py` and
  `tests/test_report_hashing.py`: 317 passed. The Prompt 171 handoff's "352 passed" was a separate
  seven-file run of the same files plus `tests/test_container_files.py` (35 tests); both figures
  were actual results of different commands (reconciled in Prompt 172).
- Full suite: `2910 passed, 310 skipped`. The skips are the 308 PostgreSQL integration tests (no
  database configured, as authorized), the existing POSIX-only signal test and the existing
  symbolic-link corpus test, which this Windows user cannot run. Collection: 308 integration and
  2,912 non-integration tests (237 new, all database-independent; M5a has no PostgreSQL tests).
- `uv build --offline`: wheel and sdist built. Compared with a build of `d34aaaac` (from
  `git archive`), the wheel gains exactly the four `evidenceguard_agents` files and the two new
  domain modules, the sdist additionally gains the three new test modules (and this ADR), nothing is
  removed, and the 16 `sample_data` files are byte-identical.
- Installed wheel: the CI wheel step was extracted from `ci.yml` and run in a fresh environment
  outside the checkout, with its two install lines replaced by offline equivalents (locked
  requirements exported with hashes and installed with `--require-hashes` from the existing cache,
  then the built wheel with `--no-deps`). Every existing check and the new M5a check passed, with
  imports resolved from `site-packages`.

Not run: Linux, CI, PostgreSQL, Docker, the container smoke, any provider or network call. The
reviewer's earlier Pydantic and arithmetic probes (Prompts 168–169) were not project tests.

## Prompt 172 corrections

The external reviewer verified the Prompt 171 export (171,421 bytes, SHA-256
`0e2e8599cb0070baeec8ee0efa493a964d38724d94ab145a8c4276d350b455b1`), inspected the four new
modules, the relevant tests, the packaging and workflow changes and this ADR, and ran isolated
probes against the extracted submitted modules plus the existing domain dependencies with Python
3.12.14 and Pydantic 2.14.0 (no project suite, build, installed-wheel check, PostgreSQL, Docker or
provider call). Valid JSON parsing worked. Two findings were reproduced; these probes are separate
from Claude Code's local checks.

- **Finding A (string mode weakened Python-mode strictness).**
  `VerifierOutput.model_validate_strings({"verdict": "supported", "rationale": "r"})` returned a
  value, although direct construction and `model_validate` reject that raw enum string.
  *Correction:* `model_validate_strings` now runs the same strict Python-mode validation as
  `model_validate` (exact enum members, tuples and nested instances), so no string coercion is
  available through a Python-mode entry point. JSON text keeps using `model_validate_json` or
  `parse_output`.
- **Finding B (ordinary mapping failures exposed raw error text).** A `dict` subclass whose
  `__contains__` raised escaped `model_validate` and `model_validate_strings` as the original
  `RuntimeError`; an update mapping whose `__iter__` raised escaped `model_copy`; a scripts mapping
  whose `items()` raised escaped `ScriptedFakeProvider(...)`. Each exposed the canary through
  `str(error)`. *Correction:* each public operation now runs inside one boundary
  (`agent_outputs._guarded`, `scripted._copied_scripts`) that suppresses ordinary `Exception` only
  and raises a fresh `InvalidModelValueError` after leaving the handler, covering the whole
  operation: nested-instance traversal (`__contains__`, `__getitem__`), reading the update (now
  read once through `items()`), copying, construction and Pydantic validation, and the whole
  configuration copy. Process control propagates as the same object; exception chains are not
  inspected; nothing logs. This is error normalization for supported inputs, not a sandbox against
  malicious trusted Python code.

**Approved implementation choices (Prompt 172 review):** the Ruff `known-first-party` addition (a
package classification, not a lint relaxation), dispatching the revalidated equal request,
rejecting `WrongModel` steps that name the fake's own model, and the test-pinned Pydantic
base-init convention and Python-entry-point nested-instance checks, provided the corrected public
boundaries keep their promised behaviour. Implementation acceptance remained pending at that review
(historical; accepted for a local commit in Prompt 173).

**Regression evidence.** The 26 new regression tests use only public entry points, so all of them
ran against both versions: isolated ignored copies of the submitted (Prompt 171) and corrected
package trees were placed first on `PYTHONPATH`, and the import locations of `agent_outputs`,
`scripted` and `evidence` were confirmed to be those copies before each run.

- *Corrected modules:* 26 passed.
- *Submitted modules:* 17 failed, 9 passed. **13 failures reproduce the findings:** Finding A once
  (the raw `"supported"` accepted); Finding B four times through `model_validate` and
  `model_validate_strings` (raw canary `RuntimeError`), five times through `model_copy` (including
  the reviewer's `dict.__iter__` probe) and three times through the fake's configuration.
  **4 failures are not reproductions:** they depend on the new policy (the submitted string mode
  rejected Python enum members, which the corrected policy accepts for consistency with
  `model_validate`) or on the new read path (the submitted copy never called `items()`, so an
  `items()`-raising update and its two process-control variants did not trigger). **9 tests
  already passed** on the submitted code (the other raw-input rejections, valid JSON parsing,
  ordinary configuration and process control from the fake's configuration).

## Verification (Prompt 172, local Windows, Claude Code)

In the existing locked environment (`uv … --locked --offline`; no dependency or lockfile change),
on Windows only; Linux and CI have not run.

- `ruff check .` and `ruff format --check .`: clean (186 files). Strict `mypy`: no issues in 148
  source files.
- Regression comparison as above.
- Focused: the six-file command 343 passed; the seven-file command (adding
  `tests/test_container_files.py`) 378 passed.
- Full suite: `2936 passed, 310 skipped` (308 PostgreSQL tests without a database, one POSIX-only
  signal test, one symbolic-link test this Windows user cannot run). Collection: 308 integration
  and 2,938 non-integration tests.
- `uv build --offline`: wheel and sdist built. Compared with the Prompt 171 baseline build of
  `d34aaaac`, the wheel again gains exactly the four agents files and two domain modules, nothing
  is removed, and the 16 `sample_data` files are byte-identical.
- Installed wheel: the extracted CI wheel step (offline, locked requirements with hashes, the wheel
  with `--no-deps`) passed every existing check and the M5a check in a fresh environment outside
  the checkout, and a direct probe of the corrected entry points against the installed wheel
  (string-mode raw enum rejection, failing-mapping normalization in `model_validate`,
  `model_validate_strings`, `model_copy` and the fake's configuration, process-control identity
  and valid JSON parsing) passed with imports from `site-packages`.

Not run: Linux, CI, PostgreSQL, Docker, the container smoke, any provider or network call.

## External review (Prompt 173)

**Decision.** The external reviewer accepted the corrected M5a implementation at external review in
Prompt 173 **for a local commit only**, pending Linux and current-version CI. No publication or
merge is authorized. None of the 308 integration tests has run against this version, and M5a adds
no PostgreSQL tests. M5b–M5h and overall M5 acceptance remain pending.

**Reviewer evidence and its scope.**

- *Prompt 171:* the reviewer independently verified the original attachment's byte size and
  checksum (`.local/p171/m5a-implementation.diff`, 171,421 bytes, SHA-256
  `0e2e8599cb0070baeec8ee0efa493a964d38724d94ab145a8c4276d350b455b1`) and inspected its
  implementation, relevant tests and packaging and workflow changes.
- *Prompt 172:* the reviewer inspected the complete pasted correction diff. The export file itself
  was not supplied, so the reviewer did **not** independently verify that file's bytes or checksum
  (`.local/p172/m5a-validation-boundary-corrections.diff`, 67,685 bytes, SHA-256
  `30488346e80cdb0aff73f89385a7f7b5a941e64d1a1ad7dfa7e7f4aca9f03f7e`). Claude Code verified that
  file against its Git comparison locally in Prompts 172 and 173; that is Claude Code's
  verification, not the reviewer's.
- *Isolated checks:* the reviewer reconstructed the functional corrections in isolated review
  copies and ran 22 checks with Python 3.12.14 and Pydantic 2.14.0, covering raw-enum rejection,
  fixed private errors from mapping operations, identity preservation for `KeyboardInterrupt`,
  `SystemExit` and `GeneratorExit`, valid JSON parsing, valid Python construction, copying, and
  completed and refusal provider outcomes. All 22 passed. These were isolated reviewer checks on
  reconstructed copies, not byte-verified copies of the full corrected export, and not a project
  suite, regression suite, installed-wheel check, build, PostgreSQL, Docker or live-provider run.

**Claude Code evidence relied on (Prompt 172, local Windows; historical, not exact-commit CI).**
Corrected targeted regressions 26 passed; against the submitted modules 17 failed and 9 passed
(13 genuine reproductions, 4 non-reproductions); focused six-file command 343 passed and seven-file
command 378 passed; full suite `2936 passed, 310 skipped`; collection 308 integration and 2,938
non-integration tests; Ruff, strict mypy, the offline build, the isolated installed-wheel checks
and the direct installed-wheel boundary probe passed. Prompt 173 changes documentation and history
only; the implementation, tests, packaging and workflow are byte-identical to the accepted tree
`5d4febb6`, so these checks were not repeated.

**Approved choices remain recorded:** the Ruff `known-first-party` addition, dispatching the
revalidated equal request, rejecting `WrongModel` steps that name the fake's own model, the
test-pinned Pydantic base-init convention and the Python-entry-point nested-instance checks.

**Pending:** publication and merge (unauthorized here), Linux verification, current-version CI
including the PostgreSQL integration job and the installed-wheel check on both platforms, and
overall M5 acceptance. *(Historical at Prompt 173: publication and feature-branch CI followed in
Prompt 174, below; merge and overall M5 acceptance remain pending.)*

## Feature-branch CI evidence (Prompt 174)

**Publication.** Prompt 174 first recorded the publication authorization in the history-only commit
`9ba6a48888ff39a06b336a22429d5b3dcfa0bad6` (`prompts.md` only; parent `79e32532`, the accepted
implementation). The first push was cancelled while Git Credential Manager awaited an account choice
(exit 128, nothing published). After Mathew returned, Claude Code re-verified the local and remote
state (remote `main` `46c02257`, no remote feature branch, the 12 implementation, test, packaging and
workflow blobs identical to the accepted tree `5d4febb6`) and ran
`git push --set-upstream origin refs/heads/feat/model-call-contracts:refs/heads/feat/model-call-contracts`
once: exit 0, remote `feat/model-call-contracts` = `9ba6a488`, remote `main` unchanged. **Not
merged at that observation; `main` was `46c02257`.**

**Runs** (both for head SHA `9ba6a488`, event `push`, branch `feat/model-call-contracts`, attempt 1,
completed with conclusion `success`; the API listed exactly these two runs for the SHA):

| Run | Job | Steps (API) | Log results (retrieved by the external reviewer) |
|---|---|---|---|
| [CI 39303677105](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105) | [Ubuntu verify 118235104286](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105/job/118235104286) | success; checkout, uv and Python 3.12, locked install, formatting, lint, type-check, test, build distribution and the installed-wheel step all succeeded | `2938 passed, 308 skipped in 26.62s`; installed-wheel lines below |
| | [Windows verify 118235103507](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105/job/118235103507) | success; the same steps all succeeded | `2937 passed, 309 skipped in 59.65s`; installed-wheel lines below |
| | [PostgreSQL integration 118235104321](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105/job/118235104321) | success; container initialization, checkout, uv, locked install, database readiness and "Run integration tests" succeeded | `308 passed, 2938 deselected in 189.30s`; the 104 M4 PostgreSQL cases passed, including both Voyage cases (M5a adds no PostgreSQL tests) |
| | [Container 118235103996](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677105/job/118235103996) | success; all six required steps (Compose validation, build-context check, image build, image check, Compose smoke, cleanup) succeeded | effective build context 95 files with 19 planted fixtures excluded; image checks passed; smoke and cleanup succeeded (summary below) |
| [Secret scan 39303677129](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677129) | [Gitleaks (full history) 118235103782](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39303677129/job/118235103782) | success; full-history checkout, checksum-verified install and the history scan succeeded | 75 commits scanned; no leaks found |

No required job or step was skipped, cancelled or incomplete.

**Installed-wheel output.** Both installed-wheel logs (Ubuntu and Windows) printed these six lines:

- offline embedding, canonical storage and indexing modules ran from the installed wheel
- retrieval modules imported and fusion ran from the installed wheel
- evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
- Voyage adapter validated a mocked response from the installed wheel
- model-call contracts classified a scripted fake response from the installed wheel
- offline migration SQL rendered from the installed wheel

The M5a line is the first CI evidence of the new package from an installed wheel. The Recall@5 line
is pure arithmetic over a fixture, not a database-derived corpus Recall, and the Voyage line uses a
mocked response.

**Container smoke (reported checks).** The smoke reported a healthy stack, an accepted upload (202),
successful ingestion, an active revision with 2 verified chunks, a duplicate upload returning the
existing revision (200), one offline indexing job, a ready index with 2 embeddings and a successful
indexing job, and an idle-worker exit 0 without an OOM kill. These are the smoke's own reported
checks, not independent inspection of the underlying database rows. The smoke is unchanged from M4
and covers offline ingestion, indexing and idle-worker shutdown only; **it does not exercise M5a**.

**Attribution.**

- *Claude Code (Prompt 174):* observed the run, job and step records above through the anonymous
  GitHub REST API only. Its job-log downloads returned **HTTP 403** ("Must have admin rights to
  Repository."), and no authentication was changed; at that point the log details were unobserved.
- *External reviewer (after Prompt 174, recorded in Prompt 175):* independently retrieved both
  workflow-run records, all five job records and all five job logs for `9ba6a488`; the counts, the
  wheel lines, the container summary and the Gitleaks count above come from those logs. The reviewer
  ran no project suite, build, installed-wheel check, database, Docker or provider locally.
- The Prompt 171–172 local Windows checks and the reviewer's isolated Prompt 173 checks above remain
  separately attributed.

**Scope.** This is contract evidence for the M5a values and the scripted fake, not live-model
quality. When this evidence was recorded (Prompts 174–176) M5a was **unmerged** and `main` was
`46c02257`.

**Acceptance and publication authorization (Prompt 176).** The external reviewer accepted this
feature-branch CI evidence (Prompts 174–175) in Prompt 176, after independently verifying the
Prompt 174 and Prompt 175 export files' byte sizes and checksums and inspecting their documentation
changes; the reviewer's earlier log retrieval keeps its recorded scope, and no M5b implementation or
project test was run for that review. Prompt 176 authorized a local documentation commit,
publication of the feature branch and, only after all five required jobs pass for that exact new
commit, a fast-forward of `main`. At the time of this record that publication was **pending
execution**; no merge or new CI result is claimed here.

*(Historical: the authorized publication ran in Prompt 176 after the feature gate passed; see
below.)*

## Main publication evidence (Prompts 176–177)

**Publication (Prompt 176, Claude Code).** The documentation commit
`f04e09576e0ed358669f793c134d9dbc30141104` (parent `9ba6a488`, tree `3d48bdac`; documentation and
history only, the 12 implementation, test, packaging and workflow blobs identical to `5d4febb6`)
was pushed to `feat/model-call-contracts` (exit 0). After all five required jobs passed for that
exact commit, `main` was fast-forwarded from `46c02257` to `f04e0957` and pushed (exit 0); the
publication range was exactly `d34aaaac`, `79e32532`, `9ba6a488` and `f04e0957` with the 18 reviewed
paths. **M5a and the accepted M5b specification are on `main` at `f04e0957`.**

**Runs and jobs.** All four runs used event `push`, attempt 1 and the exact SHA `f04e0957`, on the
branch shown; every required job and step succeeded, none skipped. Log results are from the logs
independently retrieved by the external reviewer:

- Feature branch `feat/model-call-contracts`:
  - [CI run 39309049137](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137)
    - [Ubuntu verify 118253589023](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137/job/118253589023): `2938 passed, 308 skipped in 29.80s`
    - [Windows verify 118253588640](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137/job/118253588640): `2937 passed, 309 skipped in 60.14s`
    - [PostgreSQL integration 118253589210](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137/job/118253589210): `308 passed, 2938 deselected in 138.89s`
    - [Container 118253588979](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049137/job/118253588979): successful
  - [Secret-scan run 39309049185](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049185)
    - [Gitleaks 118253587912](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309049185/job/118253587912): 76 commits scanned, no leaks
- `main`:
  - [CI run 39309653878](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878)
    - [Ubuntu verify 118255627355](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878/job/118255627355): `2938 passed, 308 skipped in 36.52s`
    - [Windows verify 118255627999](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878/job/118255627999): `2937 passed, 309 skipped in 77.82s`
    - [PostgreSQL integration 118255627842](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878/job/118255627842): `308 passed, 2938 deselected in 168.33s`
    - [Container 118255629020](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653878/job/118255629020): successful
  - [Secret-scan run 39309653917](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653917)
    - [Gitleaks 118255627517](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39309653917/job/118255627517): 76 commits scanned, no leaks

**Observed in the logs (both pushes).** The 104 M4 PostgreSQL cases passed: 29 embedding, 18
indexing, 39 retrieval, 16 evaluation and 2 Voyage cases (M5a adds no PostgreSQL tests). All four
installed-wheel logs printed the same six lines as at `9ba6a488` (above), including "model-call
contracts classified a scripted fake response from the installed wheel". Both container logs
reported an effective build context of 95 files with 19 planted fixtures excluded, successful image
checks, a healthy database, migration and API stack, an accepted upload (202), successful ingestion
and an active revision with 2 verified chunks, a duplicate upload returning the existing revision
(200), one offline indexing job, a ready index with 2 embeddings and a successful indexing job, an
idle-worker exit 0 without an OOM kill, and successful smoke and cleanup.

**Attribution and scope.**

- *Claude Code (Prompt 176):* published the commit, observed the run, job and step conclusions
  through the anonymous GitHub API only, and could not retrieve the logs (feature logs HTTP 403;
  main CI logs no HTTP response, main Gitleaks log HTTP 403).
- *External reviewer (recorded in Prompt 177):* checksum-verified and inspected the Prompt 176
  acceptance export, retrieved the commit and remote-branch records (both `main` and
  `feat/model-call-contracts` at `f04e0957`), all four workflow-run records, all ten job records and
  all ten job logs. The reviewer ran no project suite, build, wheel check, PostgreSQL, Docker or
  provider locally.
- The container details are the smoke's own reported checks, not independent inspection of
  database rows; the smoke does not exercise M5a or M5b. M5a evidence is scripted-fake contract
  evidence, not live-model quality; the wheel's Recall@5 line is arithmetic, not a database-derived
  corpus Recall. The earlier `9ba6a488` feature evidence above keeps its own counts and attribution.

## Limits

- **No production use:** nothing registers, configures or networks a provider; the scripted fake
  is a contract fixture, never quality evidence. Provenance checks, prompts, request assembly,
  persisted snapshots and orchestration are later slices; the M4d trusted-snapshot limitation is
  unchanged.
- **Timing:** `timeout_ms` is passed to adapters; `call_validated` imposes no hard deadline and
  cannot interrupt a blocking provider. Latency is descriptive.
- **Privacy** covers public errors, default representations and logs. It does not cover trusted
  code inspecting frame locals or held values, `model_dump` and attribute access (which return
  content by design), or bypasses such as `model_construct` and `object.__setattr__`.
- **Pydantic coupling:** choice 1 relies on a Pydantic source convention, pinned by tests.
- Bounds are engineering defaults, not measured limits.
- **Verification scope:** M5a changes neither the container smoke (offline ingestion, indexing and
  idle-worker shutdown only) nor its scope; local Compose remains unverified. No semantic-quality,
  injection-resistance or production-readiness guarantee is made.
