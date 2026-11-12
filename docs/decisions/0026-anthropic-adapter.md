# ADR-0026: Anthropic adapter and HTTPS transport

- **Status:** M5h is **reviewed, verified in CI and on main** at
  `e050da3e3415d73f83db86763617d5b5f0874aeb`, within its accepted scope (Prompt 231).
  Claude Code implemented it in Prompt 228; the external reviewer accepted the implementation
  and all nine choices in Prompt 229 and the Prompt 230 feature evidence in Prompt 231.
  Mathew manually pushed the evidence commit to the feature, all five fresh feature jobs passed,
  Codex fast-forwarded local main with `--ff-only`, and Mathew manually pushed main. All five
  separate main jobs then passed for the same exact SHA, `push`, attempt 1. This publication
  evidence was accepted externally in Prompt 232; it was not in that CI target. The separate
  overall M5 assessment/hold recommendation was accepted in Prompt 233; overall M5 is still
  unaccepted. Its bounded completion specification was accepted in Prompt 234; the
  implementation was accepted for one local commit only in Prompt 235. After separately
  authorized manual feature publication, it is [feature-CI verified, not merged](../plan.md#m5-completion-feature-ci-evidence-prompt-236)
  at `2a388dc324950d9feb46dbba3ffb75222f2a938e` (Prompt 236). The reviewer accepted that
  [feature evidence in Prompt 237](../plan.md#m5-completion-feature-evidence-acceptance-and-database-mutation-status-prompt-237);
  local database mutation work was blocked by unavailable Docker tooling. Database-dependent
  mutations, main publication and renewed overall M5 assessment remain pending. Prompt 238
  accepts the blocker record and permits the same probes in existing CI PostgreSQL; the
  [runner preparation](../plan.md#m5-completion-ci-mutation-preparation-prompt-238-staged-for-review)
  was accepted for one local commit and manual feature publication in Prompt 239
  ([decision and pending exact-commit gate](../plan.md#m5-completion-ci-mutation-runner-acceptance-prompt-239)). The reviewer reports
  95 isolated standard-library checks; these are not PostgreSQL or CI execution. Database
  mutation execution remains pending; G1-G3 and overall M5 remain open.
- **Specification:** the [accepted M5h specification](../plan.md#m5h-anthropic-adapter-specification-accepted-at-review-prompt-227-implementation-pending),
  accepted in Prompt 227 with H1–H10 and binding clarifications A–C
  ([acceptance](../plan.md#m5h-acceptance-prompt-227)). The specification binds this
  implementation; nothing here changes it.
- **Preceding evidence:** M5a–M5g are reviewed, verified in CI and on main within their recorded
  scopes (M5g at `bebd2f75`, [ADR-0025](0025-review-orchestration.md)). The scoped M4d/E7
  acceptance (Prompt 226) is unchanged. That evidence is theirs; nothing below re-attributes it.

## Decision

Implement the accepted contract as specified, in two modules:

- **`evidenceguard_agents.anthropic`** (pure: standard library, the domain and M5a's
  `ModelCallTimeout`).
  - The public constants and the 19 fixed `AnthropicErrorCode` members.
  - `AnthropicError`, whose message is its code.
  - `AnthropicResponse`, with a safe representation.
  - The `AnthropicTransport` protocol.
  - `build_request_body` and `parse_response`.
  - `AnthropicProvider`, which satisfies M5a's `ModelProvider`.
- **`evidenceguard_worker.anthropic_http`.** `HttpsAnthropicTransport`, over `http.client` with
  verified TLS, a printable-ASCII `SecretStr` key and an injectable connection factory and clock.
  It imports only `evidenceguard_agents.anthropic`, the domain, `pydantic` and the standard
  library.

Nothing constructs either class outside tests. `run_review` stays unregistered, and there is no
setting, environment read, credential, endpoint or default model.

## How the contract is implemented

- **Request (M5h-C steps 1–3, M5h-D).**
  - **Revalidation.** `generate` rebuilds the request with M5a's rule (exact type,
    `dataclasses.replace`, unchanged schema and digest) and uses only the rebuilt value.
  - **Body.** The canonical, `ensure_ascii` body has exactly `max_tokens`, `messages`, `model` and
    `system`. The maximal valid request is exactly 2,784,148 bytes (tested).
  - **Calls.** An invalid request or an over-cap body makes zero transport calls; a valid dispatch
    makes exactly one.
- **Transport failures (step 4).** These are classified by their own type only:
  - process control propagates as the same object;
  - `ModelCallTimeout` and `AnthropicError(TIMEOUT)` become a fresh `ModelCallTimeout`;
  - the five kept codes are kept in a fresh error;
  - anything else is `transport_failed`.

  Errors are raised outside every handler.
- **Response admission (clarification A).** `parse_response` first requires exactly an
  `AnthropicResponse` and rebuilds it from its fields:
  - an unreadable field, a wrong type or an out-of-range status is `malformed_response`;
  - an over-cap body is `response_too_large`, whatever the status, including 504.

  Only after admission:
  - an admitted 504 becomes `ModelCallTimeout`, without JSON inspection;
  - another admitted non-200 body of 1–65,536 bytes is inspected for a strict `timeout_error`
    envelope (`type` and `error.type` only); any defect means "no envelope", and the status
    decides;
  - a 200 runs V1–V9.
- **Strict JSON (J1–J7, clarification C).**
  - **Size** is checked first.
  - **Encoding.** A leading BOM is refused, and the body must decode as strict UTF-8.
  - **Depth.** A linear pre-scan visits only quotes, backslashes and brackets, tracking strings and
    escapes, and refuses nesting deeper than 16. The recursive decoder never sees an over-deep
    input.
  - **Decoding** uses `object_pairs_hook`, which refuses duplicates at every depth;
    `parse_constant`, which refuses the named non-finite constants; a guarded `parse_float`,
    which refuses a non-finite conversion such as `1e999`, even in ignored fields; and a
    `parse_int` that refuses literals over 20 digits.
- **200 validation (V1–V9).**
  - **Envelope.** Checked for every stop reason; `id`, `stop_sequence`, `stop_details` and unknown
    fields are ignored.
  - **Other stop reasons** carry empty text, and their block payloads are not inspected.
  - **`end_turn`** needs exactly one `text` block:
    - thinking blocks are skipped;
    - citations must be absent, `null` or `[]`;
    - any other block type is malformed;
    - an escaped lone surrogate is malformed;
    - text over 65,536 UTF-8 bytes is `output_too_large`, checked last.
  - **Model echo.** `model_used` is the response `model` verbatim, so M5a's mismatch precedence
    applies only to a valid `ProviderResponse`.
- **HTTPS phases (M5h-C).**
  - **Order.** Arguments are checked first (zero clock readings and zero factory calls on a
    refusal); then the start reading; connect (then `auto_open = 0`); send and headers, each with
    the socket required; then the status, validated before the post-header elapsed check
    (clarification B).
  - **200 path.** Every later ordinary failure replaces the status: `timeout`, `clock_failed`,
    `malformed_response` (framing), `response_too_large` or `transport_failed`.
  - **Error path.** Any ordinary failure in the post-header check, the framing or the bounded
    reads, including a clock failure, yields a freshly built `AnthropicResponse(status, b"")`. The
    read cap is `min(max_response_bytes, 65,536)`.
- **Cleanup.** The response and the connection are closed separately, each at most once. Ordinary
  close failures are ignored. The first process-control object is re-raised as the same object
  after both closes; later ones are suppressed.

<a id="implementation-choices-for-review"></a>

## Implementation choices accepted at external review (Prompt 229)

The reviewer accepts all nine choices below. No production, test, packaging or workflow
correction is requested. The accepted specification and all earlier milestones are unchanged.

1. **Elapsed rechecks on the error path.** The error path applies the same elapsed check after
   each read as the 200 path. A budget spent after the last error-body read therefore yields a
   status-only response: the body is dropped and the status is kept.
2. **Admission order.** The `AnthropicResponse` constructor checks the status, then the body type,
   then the body length. A value that is both mistyped and oversized is `malformed_response`.
3. **Depth pre-scan.** Outside strings, a backslash is not interpreted; it is left to the decoder,
   which refuses it. Unbalanced brackets are also left to the decoder.
4. **Backwards clock.** A reading is compared with the previous reading of the same call only.
   Integer readings are converted to `float` after the bounds check.
5. **The transport's request cap.** The transport uses the adapter's `MAX_REQUEST_BYTES` as
   imported at module load. A test that patches the adapter's cap does not change the transport's
   check.
6. **The constructor's validity check.** It is wrapped in `except Exception`, so an ordinarily
   raising `SecretStr` accessor is a fresh `configuration` error, while process control propagates.
7. **`_status_code` is private.** The status-to-code mapping is not part of the accepted public
   surface.
8. **The response is built after cleanup.** The transport's `run` returns `(status, body)`, and
   `post` builds the `AnthropicResponse` after both closes. The status-only value on the error
   path is therefore always a new object.
9. **Packaging guards.**
   - `anthropic.py` joins the accepted agents modules.
   - `anthropic_http.py` is the only new worker module importing `evidenceguard_agents`, and a
     dedicated guard restricts that import to `evidenceguard_agents.anthropic`.
   - A text scan confirms nothing outside the two modules names `AnthropicProvider`,
     `HttpsAnthropicTransport` or `anthropic_http`.

## Verification run locally in Prompt 228

Claude Code reported the checks below on Windows and described them as locked and offline,
bound to staged tree `5c1351859a7cb2c5800897f6c883803f3130ea85`. Saved records support the
functional checks and builds; the mutation attribution and offline qualification are recorded
under [external review](#external-review-and-implementation-acceptance-prompt-229).

| Check | Result |
| --- | --- |
| Ruff format and lint | clean (245 files) |
| Strict mypy | no issues in 199 source files |
| New M5h tests (3 modules) | 558 passed |
| Focused regressions (M5a, M5c, M5g handler and outputs, M4f, packaging) | 1,286 passed |
| Full suite | 5,560 passed, 441 skipped (439 integration skipped because `EG_TEST_DATABASE_URL` is unset; 2 Windows platform skips) |
| Collection | 439 integration and 5,562 non-integration tests; the 558 new tests collected |
| Mutation check (historical report; earlier HTTP source) | 6 injected contract violations reported caught (A, B twice, C, J3, cleanup), with restoration; exact-final-source coverage was not independently established during recovery |
| Build (offline, `git archive`) | wheel: only the 2 new modules added and `RECORD` changed; sdist: the 5 new files added and `tests/test_packaging.py` changed; the 3 wheel and 19 sdist protected resources identical |
| Installed-wheel step | the complete step from the staged `ci.yml`, in a fresh environment outside the checkout, with hashed offline requirements: exit 0, the registry line, the 12 existing result lines and the new M5h line |

**Evidence scope.**

- **The HTTPS transport**, in Claude Code's reported tests, used fake connections and a real
  `http.client.HTTPSConnection` subclass over an in-memory socket. Claude Code reported no DNS,
  TCP or TLS handshake or endpoint contact; recovery established no live-test evidence and did
  not independently establish universal historical absence of network activity.
- **Composition.** The test runs the real adapter through the M5g factory over the existing offline
  review world. It is not a registration.
- **Not run.** No PostgreSQL test (none is needed for M5h), no exact-version CI, and no live call.

## External review and implementation acceptance (Prompt 229)

**Decision.** The external reviewer accepts the submitted M5h implementation at tree
`3a474c7d8f067cbed261ab2fcdcedec052ca65c6` for a local commit only, with all nine
[implementation choices](#implementation-choices-accepted-at-external-review-prompt-229)
accepted: dropping a complete error body after a failed post-read elapsed check while preserving
the status; status, body-type, then body-length admission; leaving malformed JSON syntax to the
decoder after the depth pre-scan; comparing clocks with the previous reading of that call;
binding the request cap through the transport's module import; normalizing ordinary
`SecretStr`-accessor failures to `configuration`; keeping `_status_code` private; constructing
the response after cleanup; and the narrow packaging/import guards. No production, test,
packaging or workflow correction is requested. This changes no accepted specification or
earlier milestone.

**Reviewer evidence, as supplied in Mathew's Prompt 229.** These observations and executions
belong to the external reviewer, separately from Claude Code's saved Prompt 228 checks and
Codex's recovery observations. Codex did not run or witness these probes.

- The reviewer verified the uploaded export's SHA-256, bytes, lines, file count,
  additions/deletions and encoding, and reviewed the implementation, tests, workflow addition,
  packaging guards and this ADR.
- The reviewer extracted the exact submitted production modules from the diff and verified
  their Git blob identities:
  - `anthropic.py`: `962f0a73a212d49d5b2d12e1ad9a65b4acb36e56`;
  - `anthropic_http.py`: `b56b47e87be1328609c57d246ddd6c2165e322b6`.
- The reviewer checked supporting M5a/domain source blobs against the published `bebd2f75` tree.
- **All 73 independent isolated checks passed**, using Python 3.12.14 and Pydantic 2.13.4.
  They covered normal parsing and status mapping; `timeout_error` envelopes; malformed and
  oversized bypass-built 504 responses; non-finite numbers and oversized integers;
  non-`end_turn` block handling; clock failures and expiry before and after known statuses and
  during reads; first-interrupt identity despite later cleanup failures; close counts; and the
  2,784,148-byte maximal request.

**Reviewer limits.** The probes used synthetic inputs and fake connections. They were not the
project suite, installed-wheel checks, PostgreSQL execution, real HTTP/DNS/TLS or live-provider
tests. They establish no exact-commit CI result, live compatibility or model quality.

**Codex recovery observations and qualifications.** The saved recovery note at
`.local/p228/recovery/recovery.md` is copied into the prompt history; it is local evidence,
not a new functional run. Recovery verified the accepted Git/export identities, the saved
source binding and build artifacts. Saved records support the reported functional checks and
builds. The executable sources were unchanged since the verified functional checks: all 213
bound source/config blobs matched the tested and final trees; only five documentation/history
paths changed afterward. Recovery did not rerun those checks.

- The six-mutation record binds to an earlier HTTP-source hash: restored prefix
  `21b05b1553dcbdf0`, versus final functional-check-bound prefix `e0dcb325b911df8e`.
  Exact-final-source mutation coverage was not independently established. No mutation rerun is
  required for this acceptance.
- The mutation runner lacks `--offline`. That alone does not demonstrate network activity,
  but universal historical absence of network activity was not independently established by
  recovery. The original handoff's blanket claim remains an attributed historical report.
- Saved installed-wheel records support the complete assertion body with offline setup
  adaptations, using the tested wheel. The accepted final wheel has identical Python members
  and differs only in `METADATA` and `RECORD`; it was not separately installed in that check.

**Boundary at Prompt 229 (historical).** Acceptance authorized one local implementation commit;
publication, Linux verification and exact-version CI were then pending. Prompt 230's separate
feature publication and CI evidence follows below. No application review path, `run_review`
registration or live provider configuration is added. M5g's evidence and attribution and the
scoped M4d/E7 acceptance remain unchanged, as do U4, the M3 lease/commit-window and
unknown-outcome limits. M6 and overall M5 acceptance remain pending. No live compatibility,
model-quality, entailment, authenticity or injection-resistance claim follows.

## Feature publication and exact-commit CI (Prompt 230)

**State at Prompt 230 (historical): feature-CI verified, not merged.** Mathew manually pushed
`feat/anthropic-adapter` at **`c785ee58dfe8398cf58cbbd54f8d5705743e1949`**. The history-only
authorization commit has parent `6e0ad2b714c3cd70d398f674fe9e1934106357a0` and tree
`76a4401ba0dd3cd33c9089c11cc5dca6636dba51`; all executable blobs and modes are unchanged
from the accepted implementation. Codex verified remote feature, local HEAD and upstream
equal that target, with local main, stored origin/main and remote main still
`bebd2f7593af6459b25182adab2c3ddee17b9e31`. Codex did not push or merge.

**Current observations by OpenAI Codex.** These are retrieved GitHub run/job metadata and
decoded logs, separate from Claude Code's historical Prompt 228 local checks, the external
reviewer's isolated checks and Codex's recovery observations. Both workflows were triggered
by **`push`**, on **`feat/anthropic-adapter`**, for the exact SHA above, **attempt 1**:

- [CI run 42857388059](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059): completed, success.
- [Secret-scan run 42857388153](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388153): completed, success.

| Required job | Observed conclusion and log evidence |
| --- | --- |
| [Ubuntu verify, job 129974038029](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059/job/129974038029) | Success; **5,562 passed, 439 skipped**. Formatting, lint, strict mypy (199 source files), tests, distribution build and the clean installed-wheel step succeeded. |
| [Windows verify, job 129974037996](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059/job/129974037996) | Success; **5,561 passed, 440 skipped**. Formatting, lint, strict mypy (199 source files), tests, distribution build and the clean installed-wheel step succeeded. |
| [PostgreSQL integration, job 129974037718](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059/job/129974037718) | Success; **439 passed, 5,562 deselected**. The database-ready check, integration test step and container cleanup steps succeeded. |
| [Container, job 129974037493](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059/job/129974037493) | Success; configuration, context, image build/check, Compose smoke and cleanup succeeded; logs print `smoke: ok` and `cleanup: ok`. |
| [Gitleaks full history, job 129974027878](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388153/job/129974027878) | Success; version 8.30.1, **101 commits scanned**, no leaks found. |

**M5h module output.** Both verify logs print all-passing progress for
`test_anthropic_http.py` (185 passing positions), `test_anthropic_provider.py` (372), and
`test_review_anthropic_composition.py` (1): 558 passing positions in each runner. These are
counts of the printed progress positions, not individually named test results. Each log prints
successful wheel and sdist builds and the production-registry line plus all twelve existing
installed-wheel result lines and the new M5h line:

```text
Anthropic adapter classified a synthetic response through call_validated from the installed wheel
```

The registry output is `ingest_revision, index_revision`. The installed-wheel M5h check uses a
synthetic response and injected transport. The existing Recall@5 line is fixture arithmetic,
and the Voyage line is mocked. None is a live provider or model-quality result.

**Container scope.** Logs show the stack healthy, an accepted upload, successful ingestion,
two verified chunks, duplicate-upload reuse, one offline backfill-indexing job, a ready index
with two embeddings, an idle worker exiting with code 0, and successful cleanup. This is
ingestion/indexing smoke evidence; it does not establish an application review path or a live
model call.

**Recording and limits.** Codex began the bounded monitor at 16:43:38 UTC and observed all five
jobs successful at 16:51:44 UTC on 2026-11-10, within the 25-minute bound. Attempt-1 run/job
metadata and decoded logs for all five jobs are saved under `.local/p230/evidence/`. No CI
rerun, fix, additional commit or push was made in response in Prompt 230. That evidence was
staged for external review and was not itself part of the published SHA or CI-verified.
It was accepted in Prompt 231 below; main publication was then pending behind new CI gates
and manual pushes, completed in the later Prompt 231 record below. Previous local results remain historical;
the earlier-source mutation and historical network-evidence qualifications above are unchanged.
There is no production `run_review` registration, live provider configuration or live-provider
evidence. U4, M3 lease/commit-window and unknown outcomes, M6 and overall M5 acceptance remain
unchanged. No live compatibility, model-quality, entailment, authenticity or injection-resistance
claim follows.

## External acceptance of feature evidence and gated publication (Prompt 231)

**Decision.** The external reviewer accepts the Prompt 230 feature-CI evidence and documentation,
including the uploaded export's hash, statistics and encoding. The reviewer independently
retrieved main and feature refs, both workflow-run records, and metadata and decoded logs for
all five jobs. The reviewer confirmed remote feature
`c785ee58dfe8398cf58cbbd54f8d5705743e1949` and main
`bebd2f7593af6459b25182adab2c3ddee17b9e31`; both runs identified the exact feature SHA,
`feat/anthropic-adapter`, `push`, attempt 1, completed/success, with every step of every required
job successful. These are the reviewer's independent observations supplied in Mathew's
Prompt 231; they confirm, rather than replace, Codex's original observations above.

**Reviewer-confirmed logs.** The [CI run 42857388059](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388059)
and [secret-scan run 42857388153](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42857388153)
and their linked jobs above show:

- Ubuntu job `129974038029`: 5,562 passed, 439 skipped in 141.58 seconds.
- Windows job `129974037996`: 5,561 passed, 440 skipped in 205.63 seconds.
- PostgreSQL job `129974037718`: 439 passed, 5,562 deselected in 455.63 seconds.
- Container job `129974037493`: `smoke: ok`, `cleanup: ok`.
- Gitleaks job `129974027878`: 101 commits scanned, no leaks.

In both verify logs the reviewer confirmed strict mypy success in 199 source files; 185
passing HTTP-test positions, 372 provider-test positions and one composition-test position;
the `ingest_revision, index_revision` production registry; all twelve prior installed-wheel
result lines; and the new synthetic M5h installed-wheel line. The positions are not individually
printed test names. The earlier isolated reviewer probes, Claude Code's local results and
Codex's recovery qualifications remain separate from these CI observations.

**Authorization and gates (as recorded before publication).** Prompt 231 authorizes one local evidence commit with
parent `c785ee58`, a manual feature push by Mathew, and a fresh exact-commit feature gate.
Only after all five required feature jobs pass may Codex perform main preflight and a local
`--ff-only` fast-forward. Mathew must then manually push main, whose separate exact-commit
attempt-1 push workflows must pass all five jobs before main-publication evidence is staged.
No automatic push, merge commit, force push, rewrite, branch deletion, CI rerun or production
correction is authorized. Results at `c785ee58` are not results for the new evidence commit.
The separately observed completion of these gates is recorded below.

**Limits unchanged.** The M5h transport and installed-wheel inputs are synthetic; container
smoke covers ingestion/indexing only. No live compatibility, model-quality, entailment,
authenticity or injection-resistance claim follows. No production review path, `run_review`
registration or live provider configuration is added. The accepted specification and all
implementation/test/packaging/workflow blobs and modes remain unchanged. Recovery did not
rerun saved functional checks; the earlier-source mutation and historical network-evidence
qualifications remain binding. U4, M3 lease/commit-window and unknown-outcome limits, M6 and
overall M5 acceptance are unchanged.

## Main publication and separate exact-commit CI (Prompt 231)

**Publication.** M5h is **reviewed, verified in CI and on main** at
**`e050da3e3415d73f83db86763617d5b5f0874aeb`**, within the accepted M5h scope. The evidence
commit has parent `c785ee58dfe8398cf58cbbd54f8d5705743e1949` and tree
`a622f25c285d6aed2082865124fbe9b6c0daa387`. Mathew reported both manual pushes; Codex
independently verified the remote refs after each. Codex executed neither push.

1. Mathew manually pushed `feat/anthropic-adapter` from `c785ee58` to `e050da3e`.
2. After all five fresh feature jobs passed, Codex fetched and rechecked the exact refs, clean
   worktree, main ancestry, four-commit range and thirteen-path union. All seven accepted
   implementation/test/packaging/workflow blobs and modes were unchanged, including the
   protected PostgreSQL test blob `837136d61e1ec815a1fa2324ff596e83dc55d591`. Range privacy
   and unsuppressed range Gitleaks passed.
3. Codex ran `git switch main` and
   `git merge --ff-only e050da3e3415d73f83db86763617d5b5f0874aeb`, advancing local main from
   `bebd2f7593af6459b25182adab2c3ddee17b9e31`. Git and the main reflog record a fast-forward;
   no merge commit was created. Remote main was rechecked unchanged immediately before handover.
4. Mathew manually pushed main from `bebd2f75` to `e050da3e`. Codex verified remote main,
   local main and origin/main equal the target, with the feature ref still equal to it, then
   monitored the separate main workflows. All five main jobs passed before this evidence update.

**Observed by OpenAI Codex through GitHub read access.** All four workflow runs below identify
the same exact target SHA, event **`push`**, attempt **1**, completed/success. Feature and main
are separate observations; no counts from `c785ee58` were reused as new-target results.

- **Feature `feat/anthropic-adapter`:** [CI run 42864151197](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197),
  [secret-scan run 42864151124](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151124).
  Monitor: 2026-11-10 17:22:02–17:28:40 UTC, within its 25-minute bound.
- **Main:** [CI run 42866526228](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228),
  [secret-scan run 42866526185](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526185).
  Separate monitor: 2026-11-10 17:35:53–17:43:25 UTC, within its fresh 25-minute bound.

| Gate | Feature job and observed log result | Main job and observed log result |
| --- | --- | --- |
| Ubuntu verify | [129997856877](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856877): **5,562 passed, 439 skipped in 120.19s** | [130006223437](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223437): **5,562 passed, 439 skipped in 136.11s** |
| Windows verify | [129997856913](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856913): **5,561 passed, 440 skipped in 220.02s** | [130006223302](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223302): **5,561 passed, 440 skipped in 208.10s** |
| PostgreSQL integration | [129997856721](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856721): **439 passed, 5,562 deselected in 375.99s** | [130006222657](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006222657): **439 passed, 5,562 deselected in 390.12s** |
| Container | [129997857008](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997857008): `smoke: ok`, `cleanup: ok` | [130006223271](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223271): `smoke: ok`, `cleanup: ok` |
| Gitleaks full history | [129997857233](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151124/job/129997857233): **102 commits scanned, no leaks** | [130006219933](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526185/job/130006219933): **102 commits scanned, no leaks** |

All ten jobs succeeded. Each of the four verify jobs succeeded through formatting, lint,
strict mypy (199 source files), tests, distribution build and clean installed-wheel execution.
Each log prints 185 passing HTTP positions, 372 provider positions and one composition
position (558 total), the production-registry line, all twelve prior installed-wheel result
lines and the new line:

```text
Anthropic adapter classified a synthetic response through call_validated from the installed wheel
```

The positions are printed progress, not individually printed test names. Registry output remains
`ingest_revision, index_revision`. The M5h wheel check uses a synthetic response and injected
transport; the existing Recall@5 result is fixture arithmetic and the Voyage check is mocked.
Both container jobs succeeded through config/context/image checks, ingestion/indexing smoke
and cleanup. They do not exercise application reviews, live models or M6.

**Evidence and limits.** Codex saved initial/final metadata, verified refs, all ten decoded job
logs and parsed verify summaries separately in `.local/p231/feature-evidence/` and
`.local/p231/main-evidence/`. No log-access limitation was encountered; existing read access
was used without authentication changes. No CI rerun, correction or extra commit was made.
The accepted specification and all executable/test/packaging/workflow identities remain
unchanged. At the end of Prompt 231 this five-file publication-evidence update was staged and
uncommitted for external review; it is not part of the CI-verified target. Its external
acceptance is recorded separately in Prompt 232 below. Historical local checks, the isolated reviewer
probes, reviewer confirmation of `c785ee58`, and recovery observations retain their separate
attribution. The earlier HTTP-source mutation and historical network-evidence qualifications
remain unchanged. Publication does not accept overall M5 or authorize production review
registration, live provider configuration or calls, or M6. U4, M3 lease/commit-window and
unknown-outcome limits remain.

## Publication-evidence acceptance (Prompt 232)

**External decision.** The external reviewer accepts both Prompt 231 exports and the M5h
main-publication evidence. M5h remains reviewed, verified in CI and on main at
`e050da3e3415d73f83db86763617d5b5f0874aeb`, within its accepted scope. This acceptance
confirms the publication record; **it does not accept overall M5**. The separate
[M5 acceptance assessment](../plan.md#m5-acceptance-assessment-proposed-prompt-232-awaiting-external-review)
was authored by Codex in Prompt 232; the reviewer accepted that assessment and its hold
recommendation in Prompt 233 after independently checking the diff, original requirements and
source. This does not accept overall M5 or revoke individual slice/scoped M4d/E7 acceptance.
The [G1-G3 completion follow-up](../plan.md#m5-bounded-completion-follow-up-proposed-prompt-233-implementation-unauthorized)
is a separate specification accepted with binding clarifications in Prompt 234.
Its [implementation status](../plan.md#m5-completion-implementation-status-prompt-234-staged-for-review)
was accepted for one local commit only in Prompt 235 and is now
[feature-CI verified, not merged](../plan.md#m5-completion-feature-ci-evidence-prompt-236) at
`2a388dc324950d9feb46dbba3ffb75222f2a938e` after Mathew's separately authorized manual push
(Prompt 236). Codex's CI observations, historical local results and reviewer probes remain
separate. The [feature evidence was accepted in Prompt 237](../plan.md#m5-completion-feature-evidence-acceptance-and-database-mutation-status-prompt-237);
local mutation verification stopped before setup because Docker tooling was unavailable.
G1-G3 remain open; database-dependent mutations, main publication and renewed overall assessment
are pending. Prompt 238 accepts that blocker documentation and amends execution location to
the existing CI service; [runner preparation](../plan.md#m5-completion-ci-mutation-preparation-prompt-238-staged-for-review)
is staged for review, without a database execution claim. This does not change M5h publication
acceptance or accept overall M5.

**Independent reviewer evidence, supplied in Prompt 232.** The reviewer independently retrieved
remote main and `feat/anthropic-adapter`, both at the exact target; all four workflow-run
records; and metadata and decoded logs for all ten jobs. Every run identifies this SHA,
event `push`, attempt 1 and the correct branch. Every step of every required job succeeded.
These independently confirm **Codex's original Prompt 231 observations**, which remain
attributed to Codex in the [separate publication record](#main-publication-and-separate-exact-commit-ci-prompt-231)
above; the new confirmation does not replace them.

| Reviewer-confirmed gate | Feature: CI 42864151197 / secret-scan 42864151124 | Separate main: CI 42866526228 / secret-scan 42866526185 |
| --- | --- | --- |
| Ubuntu | [129997856877](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856877): 5,562 passed, 439 skipped in 120.19s | [130006223437](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223437): 5,562 passed, 439 skipped in 136.11s |
| Windows | [129997856913](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856913): 5,561 passed, 440 skipped in 220.02s | [130006223302](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223302): 5,561 passed, 440 skipped in 208.10s |
| PostgreSQL | [129997856721](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997856721): 439 passed, 5,562 deselected in 375.99s | [130006222657](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006222657): 439 passed, 5,562 deselected in 390.12s |
| Container | [129997857008](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151197/job/129997857008): smoke and cleanup succeeded | [130006223271](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526228/job/130006223271): smoke and cleanup succeeded |
| Gitleaks | [129997857233](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42864151124/job/129997857233): 102 commits, no leaks | [130006219933](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42866526185/job/130006219933): 102 commits, no leaks |

The reviewer confirmed that each of the four verify logs shows strict mypy success in
199 source files; 185 passing HTTP-test positions, 372 provider-test positions and one
composition-test position; the unchanged production registry (`ingest_revision, index_revision`);
and all twelve prior installed-wheel result lines plus the new synthetic M5h line. These
positions are progress output, not individually printed test names. The reviewer also verified
both uploaded exports' hashes, sizes, line counts, statistics and UTF-8 encoding:

- Feature-evidence acceptance: four files, +76/-14, 11,948 bytes, 159 lines; SHA-256
  `a5def34c933a0b598e84396e043f8bcc382d0fdbdd3fd30535ebfd0d4b57c9ce`.
- Main-publication evidence: four files, +130/-54, 32,836 bytes, 292 lines; SHA-256
  `165f6bfbe5338ea38d3688470698756a2394036033d54dc25bf99035edbca785`.

**Qualifications retained.** Current Prompt 232 recovery independently matched the saved
exports to fresh Git comparisons and verified protected source/mode identities; it did not
repeat application checks or retrieve fresh remote evidence. The saved local results,
73 isolated reviewer probes, recovery observations, earlier-source mutation qualification
and historical network-evidence qualification remain separate and unchanged. Synthetic
transport/wheel tests establish no real API behavior or model quality. Container smoke covers
ingestion/indexing only. Provenance establishes neither entailment nor authenticity nor semantic
injection resistance. Scoped M4d/E7 acceptance, U4 discarded evidence, database trust, M3's
lease/commit window, unknown outcomes and lack of exactly-once provider calls remain.
No production `run_review` registration or application review path exists. M6 approval/export,
later live evaluation and overall M5 acceptance remain separate obligations. The new
acceptance/assessment documentation is staged and uncommitted and has no new CI result.


## Remaining limitations

- **No live evidence.** The model-echo, alias, thinking and server-timeout behaviour of the real
  API is unverified. `model_mismatch` fails closed until a live run (M7).
- **No hard wall-clock bound.** DNS, several connection attempts, TLS, header parsing, internal
  read loops and cleanup can overrun the cooperative budget. No socket disposal or server-side
  cancellation is claimed.
- **Error-body loss.** When an error body cannot be read, a `timeout_error` reported under another
  status is classified as `provider_failed`.
- **Unchanged limits.**
  - no production review path or `run_review` registration;
  - U4's discarded evidence, the M3 lease/commit window and unknown outcomes;
  - no exactly-once provider call;
  - M6 approval and export;
  - the provenance-versus-semantic limits;
  - no model-quality, entailment or injection-resistance claim.
- **Publication evidence accepted:** external review in Prompt 232. M5h is reviewed,
  verified in separate feature/main CI and on main at the exact Prompt 231 target, within
  its accepted scope. Overall M5 acceptance remains pending.
  Production wiring, credentials, live calls, M6 and overall M5 acceptance remain unauthorized.
