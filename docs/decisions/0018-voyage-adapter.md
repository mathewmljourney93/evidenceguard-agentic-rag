# ADR-0018: Voyage embedding adapter over an injected standard-library transport

- **Status:** **Accepted at external review (Prompt 160); reviewed, verified in CI and on `main`
  at `5acb75e5`** (`5acb75e59edbb42035d468c2c40bb0ab81a8725a`; see
  [Main CI evidence at `5acb75e5`](#main-ci-evidence-at-5acb75e5)). All five required jobs passed
  for that exact commit on the feature push before the fast-forward and again on the main push.
  Implemented by Claude Code in Prompt 158 and corrected in Prompt 159 (two error-privacy
  boundaries and the lease-loss integration case; see [Prompt 159 corrections](#prompt-159-corrections));
  accepted for a local commit in Prompt 160 ([External review (Prompt 160)](#external-review-prompt-160));
  published on the feature branch in Prompt 161 with evidence recorded in Prompt 162
  ([feature-branch CI evidence at `84eec023`](#feature-branch-ci-evidence-at-84eec023), historical);
  published to `main` in Prompt 163. Implements the
  [accepted M4f specification](../plan.md#m4f-voyage-adapter-specification-accepted-at-review-prompt-157-implementation-pending)
  (proposed in Prompt 154, corrected in Prompts 155–156, accepted at external review in Prompt
  157), including V1–V15, N1–N13 and the Prompt 157 cleanup clarification. **Overall M4 was
  accepted at external review in Prompt 165** within the reviewed scope implemented at `5acb75e5`
  (see the [acceptance assessment](../plan.md#overall-m4-acceptance-assessment-accepted-at-review-prompt-165)); the acceptance record, committed
  locally in Prompt 165, was published on `main` at `46c02257` in Prompt 166
  ([publication evidence](../plan.md#acceptance-publication-evidence-prompt-166)), which changes
  documentation only, so this ADR's implementation baseline stays `5acb75e5`;
  local Compose is unverified.
- **Date:** 2026-10-18
- **Builds on:** [ADR-0013](0013-embeddings.md) (M4a contracts), [ADR-0014](0014-embedding-persistence.md)
  (canonical float32 storage), [ADR-0015](0015-revision-indexing.md) (the `index_revision`
  handler and provider mapping), [ADR-0016](0016-snapshot-retrieval.md) (retrieval
  orchestration).

## Decision

M4f adds a Voyage `EmbeddingProvider` behind the existing M4a contract and a standard-library
HTTPS transport injected into it. Both are **constructed explicitly by trusted code only**:
nothing registers them, production `SUPPORTED_PROVIDERS` stays offline-only, and there is no
setting, environment variable, `.env.example` entry, CLI, endpoint, automatic indexing or live
wiring. No dependency, lockfile, migration, Dockerfile, Compose or container-smoke change.
`embed_validated` and the M4c and M4d error mappings are unchanged.

## Modules

- `evidenceguard_retrieval.voyage` (pure; standard library and `evidenceguard_domain` only):
  `VOYAGE_IDENTITY = EmbeddingIdentity("voyage", "voyage-4-lite", "voyage-http-v1", 1024, "l2")`
  (fingerprint `827fb43a08091171e8eea7b14f6943506646aff6e4dafe7e6fd47cca643cc109`, pinned in the
  tests from the literal canonical JSON); `VoyageErrorCode`, `VoyageError` (one fixed code, also
  its message and only argument, plus a derived `retryable`); `VoyageResponse` (validated
  status-and-body value); the `VoyageTransport` protocol; `build_request_body`;
  `parse_response`; and `VoyageEmbedder`. `voyage-4-lite` is a *requested* model name; no
  upstream immutability is claimed.
- `evidenceguard_worker.voyage_http`: `HttpsVoyageTransport(api_key: SecretStr, *,
  connect_timeout=10.0, io_timeout=30.0, elapsed_budget=60.0, max_response_bytes=4 MiB,
  connection_factory, clock)` over `http.client` and `ssl`; it reads no environment or file.

## Behaviour (as specified)

- **Request:** one deterministic ASCII JSON body (sorted keys, compact) with `input` as a list
  in order, the caller's `input_type`, `model`, `output_dimension` 1024, `output_dtype` `float`
  and `truncation` false. M4a's `validate_request` runs first, so an invalid request makes
  **zero** transport calls; otherwise **at most one** `post` call, with no retry, pagination
  or splitting.
- **Exchange:** `POST /v1/embeddings` on `api.voyageai.com:443` with verified TLS, fixed headers
  (`Authorization`, `Content-Type`, `Accept`, `Accept-Encoding: identity`, `User-Agent`), no
  redirect, proxy, cookie, decompression or debugging. Phases: connection and TLS, sending,
  headers, status, and for 200 only framing checks and bounded reads, then a final check.
- **Status before body:** a non-200 body is never read or drained; the transport returns a
  status-only `VoyageResponse(status, b"")`. A non-200 value carrying a body is malformed.
- **200 framing:** exactly one digit-only `Content-Length` (1–20 digits, at most the cap, else
  `voyage_response_too_large`) or a sole `chunked` `Transfer-Encoding` decoded by
  `http.client`; `Content-Encoding` absent or `identity`; anything else is malformed. Reads
  request at most 64 KiB and never more than the remaining declared length; an empty read
  before the declared length is an explicit `voyage_transport_failed` (not left to
  `IncompleteRead`, which maps to the same code); a read returning a non-`bytes` value or more
  than requested fails the same way; chunked bodies over the cap are refused after at most
  `cap + 1` decoded bytes.
- **Cooperative timing:** before each phase the remaining budget is computed and a spent
  budget means the phase is not started; the factory timeout and each `settimeout` use the
  smaller of the phase timeout and the remaining budget, through the public `connection.sock`
  only while it exists; elapsed time is rechecked after each phase and before success. A late
  non-200 status keeps its classification (N4).
- **Response validation:** the complete `VoyageResponse` is revalidated (exact type,
  reconstructed from its fields), then the status, the size, strict JSON (no `NaN` or
  `Infinity` constants, no duplicate keys), the top-level shape, the exact model echo
  `voyage-4-lite`, row cardinality and indexes (rows are placed by `index`), 1024 finite
  coordinates (huge integers are malformed), usage 0 to 2^63 − 1, and finally M4a's
  `EmbeddingBatch` (norm within 1e-6, no zero vector) as `voyage_invalid_vector`. Nothing is
  renormalized, rounded or substituted; unknown fields are parsed temporarily but not retained.
- **Errors and cleanup:** ordinary failures are classified by their own type only (never their
  chain) and raised as fresh fixed `VoyageError`s outside every handler, so public errors have
  no cause or context. The response and connection are closed separately; the first
  process-control exception that escapes into adapter-owned code is re-raised as the same
  object after cleanup; ordinary cleanup failures never change the outcome, even if their chain
  holds process control; process control from cleanup beats an ordinary operation failure.
- **Through existing boundaries:** `embed_validated` turns every `VoyageError` into M4a's
  `InvalidEmbeddingError`, so M4c records `permanent_failure` for every provider failure,
  including rate limits, timeouts and server errors (the disclosed V11 retryability gap, to be
  resolved by a separately reviewed change before any live indexing), and M4d raises
  `retrieval_provider_failed`. M5 still owns job cancellation, lease precedence and retry
  policy for retrieval orchestration.

## Implementation details for review

These are implementation choices within the accepted specification, or a pre-existing defect
fixed in an authorized path; none changes an accepted contract.

1. **Plan formatting fix.** Ruff formats Python code blocks in Markdown, and the accepted M4f
   code blocks in `docs/plan.md` at `eeef0227` were not Ruff-formatted, so
   `ruff format --check .` (a CI step) failed at that commit. `ruff format docs/plan.md`
   changed only those blocks: whitespace and line breaks, plus one trailing comma in the
   `HttpsVoyageTransport` signature. No wording, heading or anchor changed.
2. **No hidden reconnect.** `http.client` reconnects automatically when `connection.sock` is
   `None` before sending. The transport therefore requires the public socket before sending
   and before `getresponse()` (`voyage_transport_failed` otherwise) and tolerates its absence
   only after the headers, as specified.
3. **`post` argument check.** A body that is not exact `bytes` or exceeds `MAX_REQUEST_BYTES` is
   `voyage_configuration` with no connection.
4. **Header tokens.** `Transfer-Encoding` and `Content-Encoding` values are compared
   ASCII-case-insensitively after stripping spaces and tabs; a `Content-Length` value has
   surrounding spaces and tabs stripped before the digit check.
5. **Own refusals versus foreign errors.** The transport signals its own refusals with a private
   exception carrying a fixed code; a `VoyageError` raised by a connection or response object is
   foreign and, classified by its own type, becomes `voyage_transport_failed`. The adapter
   still re-raises a transport's `VoyageError` fresh with its code (as specified), unless the
   code is missing, not a `VoyageErrorCode` or raises when read, which becomes
   `voyage_transport_failed` (corrected in Prompt 159; see A below).
6. **Construction.** `VoyageEmbedder` treats a raising `post` attribute as missing
   (`voyage_configuration`). The TLS context is created once per transport with
   `minimum_version` set explicitly to TLS 1.2, after argument validation and, since Prompt 159,
   inside a private error boundary (see B below). Clock results may be `int` or finite `float`.
7. **Status from the connection.** A status that is not an exact `int` from 100 to 599 is
   `voyage_malformed_response`, checked before any `VoyageResponse` is built.
8. **Public helpers and constants.** `status_code()`, `RETRYABLE_CODES`, `VOYAGE_MODEL`,
   `MAX_TEXTS` and `MAX_USAGE_TOKENS` (adapter) and `PIECE`, `MAX_SECONDS`, `MAX_KEY_LENGTH`
   and `USER_AGENT` (transport) are module-level names.
9. **Tests.** The M4d success path in the database-independent tests replaces
   `retrieve_with_vectors` with a recorder; real retrieval is the PostgreSQL case. The
   PostgreSQL module has no socket guard (the database driver's own resolution was not
   verified locally); its transport is in memory and cannot reach the network.

## Prompt 159 corrections

The external reviewer's isolated probes (the submitted modules imported with the domain
contract and Pydantic in a scratch environment; no project suite, build, wheel, database,
Docker, network or provider call) reproduced two privacy-boundary defects, corrected here:

- **A. Transport error metadata.** Prompt 158's `VoyageEmbedder._post` read `error.code` inside
  its `except` clause. A transport `VoyageError` with `code` deleted made `embed` raise a raw
  `AttributeError` chained to the original, and a subclass whose `code` property raised let that
  raw error (with its text) escape. Now the ordinary transport exception is kept only as
  transient local state; after the handler, `_transport_code` reads `code` inside a
  `suppress(Exception)` block: a real `VoyageErrorCode` is kept, and a missing, invalid or
  ordinarily raising `code` (whatever its chain holds) is `voyage_transport_failed`. The fresh
  public error is raised outside every handler; process control raised by the `code` read
  propagates as the same object. Still at most one transport call; M4a, M4c and M4d unchanged.
- **B. TLS-context setup.** Prompt 158 called `_tls_context()` in `HttpsVoyageTransport.__init__`
  outside any boundary, so a setup `OSError` escaped raw with its text. Argument validation still
  runs first (`voyage_configuration`); then `_private_tls_context` builds the same verifying
  context, classifying an ordinary failure by its own type with the existing codes
  (`TimeoutError` → `voyage_timeout`, anything else → `voyage_transport_failed`) and raising a
  fresh fixed error outside the handler. Process control propagates unchanged. There is no
  insecure fallback, retry, connection or credential change, and no new code.
- **C. Lease-loss integration case.** The mocked M4c integration now also makes lease loss
  observable during the Voyage call (deterministic state, no sleeps), which then fails with a
  `VoyageError` or an ordinary error; the handler's `ctx.check()` raises `LeaseLostError` before
  any permanent classification, and nothing is written, finished or marked ready. The
  production handler and runtime are unchanged.

**Regression comparison.** The new targeted cases (27 in `tests/test_voyage_adapter.py`, 10 in
`tests/test_voyage_http.py`) ran against temporary copies of the saved Prompt 158 modules
(`.local/p159/old/`, first on `PYTHONPATH`, import locations confirmed) and against the
corrected modules: 26 passed and 11 failed before; all 37 passed after. **All 11 failures
reproduce the findings:** A 6 (a deleted `code`; a raising `code` property for `RuntimeError`,
`AttributeError`, `ValueError` and `TimeoutError`; and one with process control in its chain);
B 5 (a TLS-setup `OSError`, `ssl.SSLError`, `ValueError`, `TimeoutError`, and one with process
control in its chain). Each of the 11 escaped as a raw exception. Where a canary was supplied in
the escaping error (the four raising-property cases, the chained-property case and all five
TLS-setup cases), the canary was exposed; the deleted-`code` case escaped as a raw
`AttributeError` because `code` was missing, and its message need not contain a canary
(corrected wording, Prompt 160). **The 26 that passed before are not counted as reproductions:** 11 valid-code
preservation cases, 4 invalid-code cases, 2 process-control-identity cases for the `code`
property, 3 TLS process-control cases, the validation-precedes-TLS case and the real TLS context
properties already held, and the 3 lease-loss cases and the successful-finish case exercise the
unchanged handler. No case depended on a new seam except that the TLS tests patch the existing
`_tls_context` function. The corrected files were confirmed in place afterwards.

## External review (Prompt 160)

The external reviewer inspected `.local/p158/m4f-implementation.diff` (197,721 bytes, SHA-256
`aa1c4e729de63c414b5fbdede91de047604a265fa18ed07271c07a390110e888`) and
`.local/p159/m4f-error-boundary-corrections.diff` (90,300 bytes, SHA-256
`4c126b188bf9d83852b91a0351c9f9c0c011850a609aa3535589672a101db8a5`), independently matched both
sizes and checksums, and **accepted the corrected implementation for a local implementation
commit only, pending current-version CI**. Accepted scope: the pure adapter and the explicitly
constructed standard-library transport; the Prompt 159 metadata and TLS-setup privacy
corrections; the lease-loss integration coverage; the disclosed Prompt 158 implementation
choices; the formatting-only correction to the plan's Python code blocks; the narrow mocked
installed-wheel workflow addition; and the two PostgreSQL cases with an in-memory Voyage
transport, for which no blanket socket guard is required.

The reviewer reconstructed the corrected modules from the two exports and ran eight isolated
checks: a missing transport error `code` and a `code` property raising an ordinary
canary-bearing error each became a private `voyage_transport_failed`; a TLS-setup `OSError`
became a private `voyage_transport_failed` and a TLS-setup `TimeoutError` a private
`voyage_timeout`; and `KeyboardInterrupt` and `SystemExit` from the code metadata and from TLS
setup preserved object identity. The four ordinary-error checks also verified no cause or
context and no canary in the default formatted tracebacks. **The reviewer ran no project
suite, regression suite, build, installed-wheel check, PostgreSQL, Docker, network or provider
call**; these isolated checks are separate from Claude Code's checks below.

**Outstanding at Prompt 160 (historical):** Linux and current-version CI; the two new
PostgreSQL cases (then written and collected, never executed); every integration test against
this implementation; and publication, which was not then authorized. The CI items were closed by
the [feature-branch CI evidence at `84eec023`](#feature-branch-ci-evidence-at-84eec023), and
publication by the [main CI evidence at `5acb75e5`](#main-ci-evidence-at-5acb75e5).

## Main CI evidence at `5acb75e5`

In Prompt 163 Claude Code committed the reviewed verification documentation as
**`5acb75e59edbb42035d468c2c40bb0ab81a8725a`** (parent `84eec023`), published it on
`feat/voyage-adapter`, and only after the push-triggered feature runs for that exact SHA had
passed all five jobs, fast-forwarded `main` to it and pushed. The push-triggered main runs then
passed. Relative to `84eec023`, `5acb75e5` changes verification documentation and prompt history
only (README, ADR-0018, plan, threat model and prompts.md); the adapter, transport, tests and
workflow are unchanged.

**Attribution:** in Prompt 163 Claude Code observed only run, job and step conclusions through
the anonymous public API; its anonymous log downloads returned HTTP 403 for all ten jobs. For
Prompt 164 the external reviewer independently retrieved all four run records, all ten job
records and all ten job logs; the counts and output below come from that retrieval. The
reviewer ran no local project test, build, wheel check, database, Docker or provider call.

All four runs used event **push**, SHA `5acb75e59edbb42035d468c2c40bb0ab81a8725a`, **attempt 1**,
and concluded **success**; all ten jobs and their required steps succeeded, none skipped.

**Feature push** (`feat/voyage-adapter`, before the fast-forward):
[ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552620)
and [secret-scan run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552592).

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552620/job/117710964721) | `2675 passed, 308 skipped in 36.47s` |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552620/job/117710964455) | `2674 passed, 309 skipped in 78.22s (0:01:18)` |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552620/job/117710964654) | `308 passed, 2675 deselected in 195.36s (0:03:15)`; both tests in `tests/test_voyage_postgres.py` passed |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552620/job/117710964697) | all six required steps succeeded |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39139552592/job/117710964179) | 70 commits scanned, no leaks found |

**Main push** (`main`, after the fast-forward):
[CI run 39140072984](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072984)
and [secret-scan run 39140072964](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072964).

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072984/job/117712498197) | `2675 passed, 308 skipped in 30.23s` |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072984/job/117712498176) | `2674 passed, 309 skipped in 79.26s (0:01:19)` |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072984/job/117712498063) | `308 passed, 2675 deselected in 188.45s (0:03:08)`; both tests in `tests/test_voyage_postgres.py` passed |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072984/job/117712498228) | all six required steps succeeded |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39140072964/job/117712498113) | 70 commits scanned, no leaks found |

On both pushes both platforms ran tests, distribution builds and installed-wheel checks
successfully. All four installed-wheel logs printed:

```text
offline embedding, canonical storage and indexing modules ran from the installed wheel
retrieval modules imported and fusion ran from the installed wheel
evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
Voyage adapter validated a mocked response from the installed wheel
offline migration SQL rendered from the installed wheel
```

Both container logs reported (observed log summaries and successful gates, not independent
inspection of raw database rows or credentials): 89 context files with 19 planted fixtures
excluded; a healthy stack and successful migrations; upload 202, successful ingestion with two
verified chunks and a duplicate upload 200; one offline backfill indexing job, a ready index
with two embeddings and a succeeded indexing job; idle-worker exit 0 without OOM; successful
smoke and cleanup. The smoke covers offline ingestion, indexing and idle-worker shutdown only;
it does not exercise the live Voyage transport or M4e evaluation.

**Limits.** The Voyage wheel check and the two PostgreSQL cases use a mocked, in-memory
transport, not the live service; the 2/3 Recall line is pure arithmetic, not database-derived
corpus Recall. This evidence covers the exercised paths for this commit only and makes no live
compatibility, semantic-quality, latency, cost, injection-resistance, production-readiness or
general security claim. At that point overall M4 acceptance was pending (historical); it was
accepted at review in Prompt 165 ([assessment](../plan.md#overall-m4-acceptance-assessment-accepted-at-review-prompt-165)).

## Feature-branch CI evidence at `84eec023`

*Historical (Prompt 162): at that point M4f was verified on the feature branch and not merged,
with `main` at `0ae4c6ca`; it has since been published to `main` at `5acb75e5` (above).*

In Prompt 161 Claude Code committed the history-only commit
**`84eec02318c359579c5becbb408e113eee18ceaa`** (parent `54bab581`, the accepted implementation
commit) and published `feat/voyage-adapter`. The push-triggered
[ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135139059)
and [secret-scan run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135138841)
both used event **push**, that branch and exact SHA, **attempt 1**, and concluded **success**.
All five jobs and every step concluded success; no required step was skipped.

**Attribution:** in Prompt 161 Claude Code observed only the run, job and step conclusions
through the anonymous public API; its anonymous log downloads returned HTTP 403, so it observed
no counts or log output. For Prompt 162 the external reviewer independently retrieved both
workflow records, all five job and step records and all five logs through connected GitHub
tooling; the counts and output below come from that retrieval. The reviewer ran no local
project test, build, wheel check, PostgreSQL, Docker or provider call.

| Job | Observed |
|---|---|
| [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135139059/job/117698018663) | `2675 passed, 308 skipped in 35.21s`; formatting, lint, types, tests, distribution build and installed-wheel steps succeeded; the adapter and transport modules show passing progress output (case names not printed) |
| [Windows verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135139059/job/117698018506) | `2674 passed, 309 skipped in 77.85s`; all verification, build and installed-wheel steps succeeded; the adapter and transport modules show passing progress output |
| [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135139059/job/117698018301) | `308 passed, 2675 deselected in 155.87s`; `tests/test_voyage_postgres.py` shows two passing cases; no failed or skipped integration case. This is the first executed PostgreSQL evidence for the two M4f cases |
| [Container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135139059/job/117698018583) | all six steps executed and succeeded (configuration, context, build, image checks, smoke, cleanup) |
| [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39135138841/job/117698017626) | 69 commits scanned, no leaks found |

Both installed-wheel logs printed:

```text
offline embedding, canonical storage and indexing modules ran from the installed wheel
retrieval modules imported and fusion ran from the installed wheel
evaluation modules imported and Recall@5 = 2/3 computed from the installed wheel
Voyage adapter validated a mocked response from the installed wheel
offline migration SQL rendered from the installed wheel
```

**Container (printed summaries and passing gates, not independent inspection of raw database
rows or generated credentials):** context 89 files with 19 planted fixtures excluded; CI-built
service images confirmed; upload accepted with 202; ingestion succeeded with an active revision
and two verified chunks; a duplicate upload returned the existing revision with 200; the backfill
enqueued one offline indexing job; a ready index with two embeddings and a succeeded indexing
job; the idle worker exited 0 without OOM; the smoke succeeded. The smoke exercises offline
ingestion, indexing and idle-worker shutdown only, not the Voyage transport or M4e evaluation.

**What this establishes, on the exercised paths only.** The database-independent adapter and
transport tests passed on Ubuntu and Windows for this version: request formation, response
validation, status-before-body, framing, short-body detection, cooperative-budget checks,
configuration validation, cleanup precedence, privacy and the mocked M4c and M4d integrations,
all against fake transports, connections and clocks. The two PostgreSQL cases show that a
mocked Voyage provider (an in-memory transport returning offline-hash vectors) indexes a revision
through the real handler into pgvector with `allows_zero_vectors = false`, and that capture and
`search_snapshot` run with it. The installed-wheel line shows the packaged adapter validating
one canned response through a fake transport. None of this contacts Voyage or establishes live
model-echo, strict-framing or normalization compatibility, semantic quality, latency, cost,
injection resistance, production readiness or a general security guarantee. The 2/3 Recall
line is pure arithmetic; no live provider or numerical database-derived corpus Recall result
was observed. Earlier statements that CI was pending and that the two PostgreSQL cases had never
executed are historical.

## Tests

- `tests/test_voyage_adapter.py` (172 cases since Prompt 159; 145 in Prompt 158;
  database-independent; autouse network guard):
  pinned identity and fingerprint, exact request bytes, escaping and order, 32 texts in one
  request, every M4a request violation with zero calls, valid and reordered responses, integer
  coordinates, ignored unknown fields, 43 malformed responses (including `NaN`/`Infinity`,
  `1e400`, huge and over-long integers, duplicate keys and deep nesting), invalid and zero
  vectors, the float32 storage rejection, oversized bodies, every status mapping and
  retryability, direct-call validation of `VoyageResponse`, `parse_response` and
  `VoyageEmbedder`, transport errors and process-control identity, the unchanged
  `embed_validated` boundary, privacy with canaries, output and log capture, and mocked
  integration with the M4c handler (canonical rows, every failure `permanent_failure`,
  cancellation and, since Prompt 159, lease-loss precedence) and M4d `search_snapshot`; since
  Prompt 159 also transport error metadata (deleted, invalid and raising `code`, process control
  from it, valid codes preserved fresh).
- `tests/test_voyage_http.py` (254 cases since Prompt 159; 244 in Prompt 158;
  database-independent; fake connections, responses,
  sockets and deterministic clocks; autouse network guard; fakes fail on undefined attributes):
  exact request and TLS context, the default factory constructed without connecting, adapter
  plus transport, no redirects, failures in every phase by type, status before body with
  `read()` forbidden, every framing case, explicit short-body detection, read sizes and counts,
  released-socket (`Connection: close`) success for both framings with no reconnect or private
  access, every cooperative-budget phase, reduced timeouts, configuration validation, the
  cleanup matrix and Prompt 157 operation-versus-cleanup cases, privacy, and since Prompt 159
  TLS-context setup failures (patched setup function; ordinary, timeout and process-control
  failures, validation first, no connection). A fake returning
  late shows only the cooperative checks, not interruption of a real socket operation.
- `tests/test_voyage_postgres.py` (2 integration cases; not run locally; both passed in
  [feature-branch CI at `84eec023`](#feature-branch-ci-evidence-at-84eec023)):
  indexing a revision through the real handler with a mocked Voyage provider into pgvector
  (`allows_zero_vectors = false`, canonical vectors), and capture plus `search_snapshot` with
  it.
- `tests/test_packaging.py` (3 new cases): adapter and transport import boundaries, and
  unchanged production providers, registry kinds and installed commands, with no Voyage
  wiring in the API, persistence or worker outside the transport module.
- CI: one added command in the existing installed-wheel step runs the adapter with an
  in-memory fake transport and prints `Voyage adapter validated a mocked response from the
  installed wheel`.

## Verification (Prompt 159, local Windows, Claude Code; historical)

Locked environment, offline, no install or update; no Docker, database, network or provider
contact; no `EG_TEST_DATABASE_URL` set.

- `ruff format --check .` (177 files) and `ruff check .`: clean; strict `mypy` (140 source
  files): no issues.
- Both new database-independent modules: 426 passed. With the relevant existing indexing,
  retrieval, embedding and packaging tests: 893 passed, 2 skipped (the PostgreSQL cases).
- Full suite: 2673 passed, 310 skipped (308 integration tests without a database, the symlink
  test and the POSIX-only signal test); collection: 2983 tests, 308 integration.
- The regression comparison above.
- `uv build --offline`: sdist and wheel built. A fresh isolated installed-wheel environment
  outside the checkout (dependencies exported from `uv.lock`, installed offline with
  `--require-hashes`; the wheel with `--no-deps`) passed all nine CI wheel commands, including
  the Voyage command, from `site-packages`, and a direct installed-wheel probe confirmed the
  corrected boundaries: a deleted or raising `code` gives a private `voyage_transport_failed`
  with no cause or context and no marker in the formatted traceback, `KeyboardInterrupt` from
  the `code` property and `SystemExit` from TLS setup propagate as the same objects, a valid code
  is preserved fresh, and TLS-setup `OSError` and `TimeoutError` become private
  `voyage_transport_failed` and `voyage_timeout`.

**Not run at that point (historical; since covered by the feature-branch CI evidence):** the
two PostgreSQL cases, any Linux execution, current-version CI and Gitleaks in
CI. At that point implementation acceptance was pending (historical; accepted for a local
commit in Prompt 160).

## Verification (Prompt 158, local Windows, Claude Code; historical)

Historical, before the Prompt 159 corrections. Locked environment, offline, no install or
update; no Docker, database, network or provider contact; no `EG_TEST_DATABASE_URL` set.

- `ruff format --check .` (177 files, including this ADR) and `ruff check .`: clean, after the
  plan formatting fix (before it, `docs/plan.md` was reported as needing reformatting);
  strict `mypy` (140 source files): no issues.
- Focused tests (the three new files, `test_packaging.py`, `test_index_handler.py`,
  `test_retrieval_orchestration.py`, `test_embeddings.py`, `test_embedding_storage.py`): 653
  passed, 2 skipped (the new PostgreSQL cases).
- Full suite: 2636 passed, 310 skipped (308 integration tests without a database, the symlink
  test and the POSIX-only signal test); collection: 2946 tests, 308 integration (2 new).
- `uv build --offline`: sdist and wheel built; the wheel contains both new modules and no
  `sample_data`; the sdist's 16 `sample_data` files match the tracked corpus.
- Isolated installed-wheel environment outside the checkout (dependencies exported from
  `uv.lock`, installed offline with `--require-hashes`; the wheel with `--no-deps`): all nine
  commands extracted from the CI wheel step passed, including the new Voyage command, with
  modules resolved from `site-packages`.

**Not run at that point (historical; since covered by the feature-branch CI evidence):** the
two PostgreSQL cases, any Linux execution, current-version CI and Gitleaks in
CI. Mocked tests establish request formation, validation, bounds, cooperative timing checks,
error mapping and the stated privacy scope only; they do **not** verify live API
compatibility, semantic quality, latency, cost or production readiness. Live evaluation remains
M7.

## Limits

- **Live compatibility is unverified:** the exact model echo, the strict 200 framing, the
  normalization tolerance after float32 rounding, row order, error bodies and model
  immutability are documented uncertainties; a mismatch fails closed.
- **Timing is cooperative:** no hard wall-clock maximum. DNS, repeated connection attempts,
  TLS, header parsing and internal read loops can overrun the budget; once `getresponse()`
  releases the socket, reads keep the earlier timeout; cleanup has no deadline.
- **Process control** is preserved only where it escapes into adapter-owned code; one masked
  inside `http.client` cannot be recovered.
- **Memory:** the cap bounds accepted raw bytes only; no peak-memory figure is claimed.
- **Privacy** covers public errors, default representations, default formatted tracebacks and
  logs, not trusted code inspecting frame locals, the held key or a held response body.
- **Retryability gap (V11)** and deferred live wiring, settings and data-handling decisions
  remain; M5 snapshot obligations are unchanged.
