# ADR-0026: Anthropic adapter and HTTPS transport

- **Status:** M5h is **accepted for a local commit, Prompt 229; CI pending**. Claude Code
  implemented it in Prompt 228. The external reviewer accepts the implementation and all nine
  choices below for a local commit only; publication, Linux verification and exact-version CI
  remain pending.
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

**Boundary.** Acceptance authorizes one local implementation commit. Publication, Linux
verification and exact-version CI remain pending. No application review path, `run_review`
registration or live provider configuration is added. M5g's evidence and attribution and the
scoped M4d/E7 acceptance remain unchanged, as do U4, the M3 lease/commit-window and
unknown-outcome limits. M6 and overall M5 acceptance remain pending. No live compatibility,
model-quality, entailment, authenticity or injection-resistance claim follows.

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
- **Pending:** publication, Linux verification and exact-version CI; implementation is accepted
  for a local commit in Prompt 229.
  Production wiring, credentials, live calls, M6 and overall M5 acceptance remain unauthorized.
