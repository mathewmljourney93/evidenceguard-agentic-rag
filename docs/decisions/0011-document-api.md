# ADR-0011: Document upload and read API with a derived ingestion state

- **Status:** Accepted (M3e). The implementation (Prompt 89, corrected in Prompt 90 after review findings) was accepted at external review (Prompt 91) and is **reviewed and verified in CI on `feat/document-api` at `ccdf08d` ([CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)): Ubuntu, Windows and the full 204-test PostgreSQL integration suite (including the 26 M3e tests) passed, per job logs retrieved by the external reviewer**; see *Consequences and limits*. It was then published on `main` at `2e605e7`, where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again (Ubuntu, Windows and the 204-test PostgreSQL suite, per job logs retrieved by the external reviewer). Compose, M3f and overall M3 acceptance remain pending.
  - The specification was accepted at review in Prompt 88 (proposed in Prompt 86, corrected in Prompts 87–88).
- **Date:** 2026-10-15
- **Builds on:**
  - [ADR-0002](0002-request-ids-logging-and-errors.md): problem responses, request IDs and fixed log events;
  - [ADR-0005](0005-api-key-authentication.md) and [ADR-0006](0006-vendor-api-and-readiness.md): authentication, roles, tenant scoping and bounded offset pagination;
  - [ADR-0007](0007-durable-job-core.md): `enqueue` in the caller's transaction;
  - [ADR-0009](0009-document-revisions.md): `create_revision` and the revision lifecycle;
  - [ADR-0010](0010-document-ingestion.md): the `ingest_revision` job, chunk sets and the dead-job obligation;
  - the M3e specification in [docs/plan.md](../plan.md), accepted at review.

## Context

M3c stores revisions and M3d ingests them, but nothing creates or serves documents over HTTP. M3e adds a bounded multipart upload that creates a revision and its ingestion job atomically, read-only views of documents, revisions, chunks and jobs, and the `ingestion_state` projection that M3d made a condition of overall M3 acceptance. It changes no M3a–M3d behaviour.

## Decisions

### Modules

- `evidenceguard_api.uploads`: the bounded reader, the multipart contract and field validation. It has no FastAPI or database dependency, so it is tested with controlled async streams.
- `evidenceguard_api.documents`: the six routes, response models (`extra="forbid"`), the `DocumentStore` protocol and `DatabaseDocumentStore`. `create_app` takes an optional `document_store` (a test seam, like `vendor_store`).
- `evidenceguard_persistence.document_views`: tenant-scoped read models, `read_snapshot` and `create_upload`.
- `evidenceguard_domain.ingestion`: `IngestionState`, `derive_ingestion_state` and `lease_expired` (pure rules), plus the `ingest_revision` kind constant, which a test keeps equal to the worker's.
- `evidenceguard_observability.jsonlog`: one new reviewed event, `document.upload_inconsistent`, which carries no values.

### Multipart dependency

`python-multipart` **0.0.32** (Apache-2.0, no dependencies), added with an `exclude-newer-package` cutoff of `2026-10-01T00:00:00Z` under the dependency-age policy: it was published on 2026-06-04, more than two weeks before the cutoff. The PyPI metadata lists no vulnerabilities for 0.0.32, and OSV lists no advisory affecting it; the historical advisories (CVE-2024-24762, CVE-2024-53981, CVE-2026-24486, CVE-2026-40347, CVE-2026-42561 and CVE-2026-53537 to CVE-2026-53540) were fixed in 0.0.7 to 0.0.31. It is compatible with the locked FastAPI 0.143.0 and Starlette 1.7.0, and the full suite passes with it.

Only the low-level `MultipartParser` callback API is used. FastAPI's `Form`, `File` and `UploadFile` are not used, so no temporary file is ever created.

### Verified parser behaviour (0.0.32)

These were checked in the installed source and by tests, not assumed:

- `finalize()` is a no-op, so the reader tracks completion itself: a body is complete only if the parser reported the closing boundary (`on_end`) and every begun part ended.
- `max_size` silently stops parsing instead of failing, so it is not used; every cap is enforced by the reader.
- The header limits raise `MultipartParseError` with the fixed messages `Maximum header size exceeded` and `Maximum header count exceeded`, which map to 413; every other parser error maps to a 422 with a fixed code. The limits' counters persist across writes.
- **Header-name spans:** the parser checks a header name's size **before** validating its characters, and the span runs to the next colon or the end of the write. A single large write could therefore report a later size crossing (413) ahead of an earlier invalid character (422), so the outcome would depend on how the body was received. The reader therefore feeds everything outside part data **one byte at a time** (boundaries, part headers, the closing boundary) and part data in bounded 64 KiB slices that stop just before each possible delimiter (`CRLF--boundary`). A possible partial delimiter at the end of a received chunk is held back until the next chunk. Per-byte feeding is bounded by the header caps; it measured about 2 µs per byte locally (an observation, not a benchmark).
- A boundary followed by other bytes in mid-body is part data, not an error. A preamble before the first boundary is malformed. An epilogue after the closing boundary is discarded, but it still counts toward the total cap.
- The parser logs warnings that can quote submitted bytes, so each parser instance gets a disabled, non-propagating logger.
- **Unreported header bytes** (found at review, Prompt 90): the parser consumes some header bytes without passing them to `on_header_field` or `on_header_value`, including the colon, whitespace before a value (in `HEADER_VALUE_START`) and line endings. Header bytes reconstructed from the callbacks therefore undercount what was received: two headers of 5,000 leading spaces each passed an aggregate cap computed that way.
- **Lossy parameter parsing** (found at review, Prompt 90): `parse_options_header` ignores extended parameters such as `filename*` and `charset*` and keeps only the last of repeated names. It is therefore not used; see *Header parameters* below.

### Upload contract

As specified in the plan (section B), including the caps (2 MiB of file bytes, 2 MiB + 64 KiB total, 8 parts, 8 KiB of headers per part and per header line, 1 KiB per text field), the allowed fields and media types, and the three error phases. Implementation choices within that contract:

- The route declares no body parameters. Authentication and the role check are dependencies, then the vendor lookup (a read snapshot), then the request-header checks, before the first `receive`. Tests drive raw ASGI and assert that `receive` is never called on 401, 403, a foreign vendor or an oversized declared length.
- **The per-part header cap counts raw bytes** (corrected in Prompt 90). A part's *header region* is every byte the parser consumes in a header state: from the first byte after the boundary line's line ending, through the line ending of the empty line that ends the headers, inclusive. Every name, colon, space, tab, value and line ending is counted as received. Header regions are fed one byte at a time, so the feeder knows, before each byte, whether the parser is in a header state. The byte that would take the region past 8,192 bytes is refused with 413 before the parser sees it. Earlier bytes have been parsed already, so an earlier malformed byte still wins with 422, for any receive partitioning. The parser's own line limit (8,192 bytes per line) and header-count limit remain as backstops; neither can be reached before the region cap.
- **Header parameters** (corrected in Prompt 90) are parsed by a small strict parser for `value *( OWS ";" OWS name "=" ( token / quoted-string ) )` over RFC 9110 tokens and quoted strings. It keeps every parameter in order, including extended and repeated names, and rejects anything else. It is not a replacement multipart parser: it reads only the three header values the contract depends on. The rules:
  - **Part `Content-Disposition`:** a repeated parameter name, a `name*` or a missing `name` is `invalid_part_headers` (422). A text part with any `filename` or `filename*` is `filename_not_allowed` (422). A file part's `filename` or `filename*` is allowed and ignored.
  - **File `Content-Type`:** `text/plain` or `text/markdown` with at most one parameter, a plain `charset` equal to `utf-8` (case-insensitive, token or quoted). A `charset*`, a repeated `charset`, any other parameter or malformed syntax is a deferred 415, at the accepted phase.
  - **Request `Content-Type`:** exactly one plain `boundary` parameter; a `boundary*`, a repeated `boundary` or malformed syntax is 415.
  - Errors carry fixed codes; no parameter name or value appears in an error or log.
- Structural errors (missing or invalid `Content-Disposition` or `name`, unknown, repeated or second `file` part, a `filename` on a text part) are raised when a part's headers end. Field caps are checked as part data arrives.
- 422 entries use a fixed `loc` (`["body"]` or `["body", "<known field>"]`) and fixed types: `malformed`, `incomplete`, `invalid_part_headers`, `extra_forbidden`, `duplicate_part`, `filename_not_allowed`, `missing`, `value_error` and `invalid_content`.
- A client disconnect (Starlette's `ClientDisconnect`) ends the request before any creation call. The 400 it returns is unlikely to reach the client.

### Creation

`create_upload` runs in one `transaction` at the default READ COMMITTED isolation: `create_revision`, then `enqueue` (for a new revision, or idempotently for an unsettled duplicate, which can only add a missing canonical job), then **one** observation statement with the revision, its canonical job and `clock_timestamp()`. The route returns that observation only after the commit: 202 when created, 200 for a duplicate. The mapping:

- 409 for `DocumentConflictError` and `RevisionConflictError`;
- 404 for `VendorNotFoundError` and 403 for `PermissionDeniedError`;
- 503 for `RevisionCreateRaceError`, `JobEnqueueRaceError` and database or configuration errors;
- 500 with `document.upload_inconsistent` for `JobIdempotencyConflictError`.

### Reads

Each GET is one `read_snapshot`: `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY` as the first statement, then one `clock_timestamp()`, then the queries. It always ends with a rollback and close before the response is serialized. SQLAlchemy's psycopg pre-ping runs in autocommit, so it does not start the transaction first. Revision statements select every column except `content_text`. The canonical job is a left join on tenant, kind and `idempotency_key = CAST(revision.id AS text)`. `verified_complete` comes only from an `active` or `superseded` status.

## Consequences and limits

- **Executed locally (Prompts 89–90, Windows):** ruff, mypy and the database-independent suite. That includes partition-invariance tests, which present each mixed-fault body in one message, in many messages, split inside headers, boundaries and file data, and at seeded random cuts. It also includes the Prompt 90 regressions for raw header counting and parameter validation, which fail against the Prompt 89 reader.
- **Verified in CI (`ccdf08d`):** It was verified in CI on `feat/document-api` at `ccdf08d` (`ccdf08d3b901c348da8fbe03a87421e6d9c92ca7`; [CI run 38755179760](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760)). From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491605348) `1261 passed, 204 skipped in 18.44s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491604657) `1260 passed, 205 skipped in 33.03s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179760/job/116491605959) `204 passed, 1261 deselected in 59.29s`: the full 204-test integration suite, including all 26 M3e tests. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38755179509/job/116491603175): 37 commits scanned, no leaks found). The reviewer did not run the suite locally. These results demonstrate the tested behaviour, not a performance benchmark or a general security guarantee.
- **Verified on `main` (`2e605e7`):** It was then fast-forwarded onto `main` at `2e605e7` (`2e605e7bcf3b7b1ee90e9f12cb2acddb6950048f`, adding only documentation after `ccdf08d`), where [CI run 38758727669](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669) passed again. From job logs retrieved by the external reviewer: [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999468) `1261 passed, 204 skipped in 28.04s`, [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999418) `1260 passed, 205 skipped in 29.97s`, and the [PostgreSQL integration job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727669/job/116503999580) `204 passed, 1261 deselected in 56.65s`. The [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831) passed ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38758727831/job/116503999509): 38 commits scanned, no leaks found). Both runs were push events on `main`; the reviewer did not run the suite locally.
- **PostgreSQL tests:** the 26 integration tests in `tests/test_document_api_postgres.py` were not run locally (no authorized disposable database) and passed in that CI run. They cover:
  - atomic creation and rollback;
  - concurrent identical and different uploads through the API, meeting at a barrier;
  - duplicates of processing, superseded, failed and dead-job revisions against real rows;
  - GET never repairing a missing job, while a duplicate POST does;
  - the upload observation boundary: a claim right after the commit, with no statement after it;
  - the SQL projection, including an expired lease and terminal jobs with unsettled revisions;
  - partial chunk sets that are never verified complete;
  - interleavings inside production reads (an activation between the pointer and revision reads, a job and revision change mid-read, and a chunk batch between the count and page reads), injected deterministically through a statement hook;
  - a later upload writing on the same pooled connection after a snapshot;
  - cross-tenant 404s, GETs without writes, and end-to-end ingestion.
- The response is what the creation transaction observed. A worker can change the state immediately after the commit.
- `in_progress` is not a progress guarantee; `lease_expired` shows when an attempt awaits reclaim. `stalled` has no operator retry in v1.
- The reader relies on `python-multipart` 0.0.32's callback order and its public `state` attribute. An upgrade must re-verify the behaviour above; the tests pin it.
- Compose, M3f and overall M3 acceptance remain pending.
