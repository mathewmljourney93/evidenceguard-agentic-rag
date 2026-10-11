# ADR-0002: Request IDs, structured logging and problem+json errors

- **Status:** Accepted for review, implemented in M1c (revised after review: fixed event identifiers and reviewed public messages)
- **Date:** 2026-10-11

## Context

Every response needs a correlation ID that ties it to log lines. Logs and error responses must help operators without revealing what clients sent: credentials, evidence quotations or other submitted values. The plan calls for RFC 9457 problem details and JSON logs (plan §6 and §8).

## Decision

### Request IDs
- `RequestContextMiddleware`, a pure ASGI middleware, assigns every HTTP request an ID.
- An incoming `X-Request-ID` is accepted only when it is a **single** header holding a valid UUID of at most 64 characters. It is normalized to the lowercase hyphenated form. Otherwise a fresh UUID4 is generated.
- The ID goes into `request.state.request_id` and into a `ContextVar` (`evidenceguard_observability.context.current_request_id()`). The `ContextVar` is per task, so concurrent requests cannot see each other's IDs.
- Every response carries `X-Request-ID`, including errors. Starlette handles unexpected exceptions in its outermost middleware, outside ours, so the 500 handler reads the ID from `request.state` and sets the header itself.
- **The ID is a correlation identifier only.** A client can choose it, so it is never used for authentication, authorization or as evidence of identity.

### Logging
- The standard library only (`logging` plus a `JsonFormatter`); no new dependency.
- One `request.completed` line per request, with `request_id`, `method`, `route`, `status` and `duration_ms`, plus `error_type` (the exception class name only) for unexpected errors.
- `route` is the matched route template (for example `/items/{item_id}`), or `null` when nothing matched. **The raw path and query string are never logged.** Methods outside the standard set are logged as `OTHER`.
- **Allowlist, not redaction.** For every record it renders, the formatter writes:
  - the timestamp, level and logger name;
  - an `event` that is a **reviewed, fixed identifier**. It is looked up by the record's *unformatted* message template in `REVIEWED_EVENTS`. The formatter never calls `getMessage()` and never reads the message arguments. Any message not in the table becomes `log.unreviewed_message`, so its text, arguments and any exception interpolated into it are not copied;
  - only the allowlisted structured fields. Other fields, exception details and stack traces are dropped.
- The reviewed table holds `request.completed` and Uvicorn's own lifecycle templates, for example `server.process_started`, `server.listening` and `server.unhandled_exception`.
- No pattern-based secret matching is used. This is how the plan's "logs redact secrets" requirement is met.
- `create_app()` adds no log handlers. `eg-api` passes a `dictConfig` mapping to Uvicorn. Applying it replaces handlers rather than adding them, so several app instances, or configuring twice, never duplicate lines.
- Uvicorn's access log is disabled because it records raw paths and query strings.
- Uvicorn's error logger still records that an exception happened, as the fixed event `server.unhandled_exception`, with no message text and no traceback.

### Errors (`application/problem+json`, RFC 9457)
- Every error body has `type: "about:blank"`, `title` (the HTTP status phrase), `status` and the extension `request_id`, which matches the header.
- **HTTP errors** keep their status and headers (for example `Allow` on 405, `WWW-Authenticate` on 401 and `Retry-After`). **Their `detail` is never published as given.**
  - An ordinary `HTTPException` gets a generic sentence for its status class: *"The request could not be completed."* for 4xx, *"The server could not complete the request."* for 5xx.
  - A specific message requires `PublicHTTPException(status, PublicMessage.X)`. `PublicMessage` is an enum of reviewed, constant sentences; its only entry so far is `AUTHENTICATION_REQUIRED`.
  - Entries must never be built from submitted values, identifiers or internal exception text. Adding an entry is a code change that goes through review.
- **Validation errors** return 422 with at most 20 `errors`, each holding only `loc` and `type`. Pydantic's `msg`, `input` and `ctx` are never returned, because they can echo submitted values or custom validator text. Each `loc` part is capped at 64 characters.
- **Unexpected exceptions** return a generic 500 (`"An unexpected error occurred."`). The exception is **not suppressed**: Starlette re-raises it to the server after responding.

## Consequences and limits

- **No traceback is logged by default.** Diagnosing an unexpected error means reproducing it or adding deliberate, reviewed instrumentation. The log shows the request ID, route and exception class.
- `loc` uses field names. For an unexpected extra field in a request body, that name comes from the client, so it can appear (capped) in the 422 body. Values never do.
- **What the logging guarantees cover.** They apply to records rendered by `JsonFormatter` through `logging_config()`, which covers the `evidenceguard`, `uvicorn` and `uvicorn.error` loggers when started by `eg-api`. Other handlers, such as a root logger set up by another tool, a different `--log-config`, or another server, are outside this control.
- Messages from other libraries are **not** assumed safe. Unless their template is in the reviewed table, they appear only as `log.unreviewed_message`. This is safe but less informative: a new Uvicorn message shows up only as an unreviewed event until its template is reviewed and added. The table matches Uvicorn 0.54's templates and must be rechecked when Uvicorn is upgraded.
- `PublicMessage` relies on code review: Python cannot prove an entry contains no sensitive data. It only prevents runtime strings from becoming client-visible details.
- These are local logs on stderr only. There is no metrics, tracing or telemetry service, and no claim of production monitoring.
- The middleware handles HTTP only. WebSocket and lifespan events pass through unchanged.
