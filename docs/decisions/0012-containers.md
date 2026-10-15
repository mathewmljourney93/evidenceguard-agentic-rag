# ADR-0012: Development container image and Compose stack

- **Status:** Accepted (M3f) at external review (Prompt 100); implemented in Prompt 98 and corrected in Prompt 99 after review findings. It is **verified in CI on `feat/container-stack` at `682101b` ([CI run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459)). Ubuntu, Windows, the 204-test PostgreSQL suite and the container job (image build, effective build context, image checks, Compose smoke and cleanup) passed, per job logs retrieved by the external reviewer** (see *Consequences and limits*). It is not merged; `main` remains at `2e605e7`. Local Compose is unverified, and overall M3 acceptance is pending a separate review.
  - The specification was accepted at review in Prompt 97 (proposed in Prompt 95, corrected in Prompts 96–97).
- **Date:** 2026-10-15
- **Builds on:**
  - [ADR-0001](0001-packaging-and-layout.md): one distribution;
  - [ADR-0003](0003-plain-python-workflow.md): plain Python, PostgreSQL-backed jobs;
  - [ADR-0004](0004-persistence-foundation.md): the dependency-age policy and the digest-pinned database image;
  - [ADR-0008](0008-worker-runtime.md): the worker's signals and its *No total shutdown deadline* limit;
  - the M3f specification in [docs/plan.md](../plan.md).

## Context

The application, the sequential worker and the migrations run from a Python environment. Before M3f, only a PostgreSQL service existed in `docker-compose.yml`, and it had never run. M3f packages the existing distribution as one image and adds migration, API and worker services. It also adds a CI job that builds the image and runs a Compose smoke test. It changes no application code, migration, dependency or `uv.lock`.

## Decisions

### Verified base images

Both digests come from the accepted specification. They were re-verified on 2026-10-15 with read-only registry metadata requests (token, manifest and config blob reads; nothing pulled):

| Image | Source | Digest (multi-platform index) | Findings |
|---|---|---|---|
| `python:3.12.14-slim-trixie` | Docker Hub Official Image, `registry-1.docker.io/library/python` | `sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` | The tag resolves to this digest. It includes `linux/amd64` (manifest `sha256:44ff437b…`), whose image configuration was created on **2026-09-19**. The Docker Hub tag API reports it last updated on 2026-09-25. It meets the two-week dependency-age policy. |
| `ghcr.io/astral-sh/uv:0.13.0` | GitHub Container Registry, `ghcr.io/astral-sh/uv` | `sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168` | The tag resolves to this digest. It includes `linux/amd64` (manifest `sha256:22fbda6e…`), whose image configuration was created on **2026-10-09**. uv 0.13.0 itself was published on PyPI and GitHub on 2026-10-09. |

**Approved uv exception (Prompt 99).** The uv 0.13.0 release and its image were six days old at implementation, below the two-week dependency-age threshold. The external reviewer approved a narrow exception for **this exact builder-tool image digest only**: `ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168`.
- **Rationale:** consistency with the uv version CI already uses, and the digest the specification explicitly reviewed.
- **What it covers:** no floating tag or replacement digest; no uv binary in the runtime image (uv is copied only into the builder stage); no application dependency or `uv.lock` change; no exception for the Python base image; no broad change to the dependency-age policy.
- **What it does not claim:** compliance with the age policy, or general safety of that image.

### Image (`Dockerfile`)

- **Two stages on the same Python base:**
  - **Builder:** copies `uv` from the uv image. It installs the locked, non-dev dependencies first (`uv sync --locked --no-dev --no-install-project`), then the project as a regular wheel (`uv sync --locked --no-dev --no-editable`) into `/opt/venv`.
  - **Runtime:** copies only `/opt/venv` and `alembic.ini`, owned by root. The fixed user and group `evidenceguard` (10001:10001) has no login shell. `CMD` is exec-form `eg-api --host 0.0.0.0 --port 8000`; Compose selects the other commands.
- **What the runtime omits:** uv, compilers, the source tree, tests, documentation, Git metadata, configuration and secrets. There are no build arguments.
- **Build backend:** the project's build backend (`hatchling`) is fetched during the build, as `uv build` does in CI. Build requirements are not covered by `uv.lock`.
- **`.dockerignore`:** an allowlist (`pyproject.toml`, `uv.lock`, `README.md`, `alembic.ini`, `apps/`, `packages/`), followed by recursive re-exclusions for `.env*`, `.git`, `.local`, virtual environments, caches, bytecode, build outputs, key and certificate files, and logs. The wheel's package data (`py.typed`, `migrations/script.py.mako`) stays included.

### Compose

- **`postgres`:** unchanged: the digest-pinned image, the disposable credentials, `127.0.0.1:5433`, the health check, the volume and the init script.
- **Application services:** `migrate`, `api` and `worker` share one anchor:
  - **Image:** `build: .`, `image: ${EG_IMAGE:-evidenceguard:dev}` and `pull_policy: never`, so the application image is never pulled from a registry.
  - **Database:** `EG_DATABASE_URL` targets `postgres:5432`.
  - **Hardening:** `read_only`, a `/tmp` tmpfs, `cap_drop: [ALL]`, `no-new-privileges`, `init: true` and `restart: "no"`.
- **Startup order:**
  - `migrate` runs `alembic -c /app/alembic.ini upgrade head` once, after the database is healthy. It is the only service that migrates.
  - `api` and `worker` start only after `migrate` completes successfully.
  - `api` publishes `127.0.0.1:8000` only, and its health check calls `/readyz` with the image's Python.
- **Worker shutdown:** `stop_signal: SIGTERM` and `stop_grace_period: 60s`. The 60 s is an **external termination budget**, not a guaranteed shutdown bound. The worker's drain, cancellation and join waits are bounded supervisor waits, but a synchronous database call can outlast them (ADR-0008), and Docker sends SIGKILL when the budget expires. M3f does not change worker semantics and adds no statement timeout.

### CI verification (`container` job; verified in CI at `682101b`)

One Ubuntu job (Linux containers), with `timeout-minutes: 20`, read-only contents permission, no registry login or push, and no new third-party actions.
- **Selection:** the project name and image tag are both unique per run and attempt: `eg-ci-<run id>-<attempt>` and `evidenceguard:ci-<run id>-<attempt>`. Every step uses the same Compose file, project and image.

The steps, implemented by the stdlib-only `infra/ci/container_ci.py`:
1. **`config`:** validates the rendered `docker compose config --format json`. This step is an addition to the specification. It checks:
   - the services and image selection, `pull_policy: never`, and the hardening options;
   - loopback-only ports, and that only `migrate` runs migrations;
   - the dependency conditions, the `/readyz` health check and the worker's stop settings.
2. **`context`:** exports the committed tree with `git archive` and plants synthetic placeholder files at 19 nested paths that must be excluded. It then exports the context Docker actually sends, using a throwaway `FROM scratch` / `COPY . /` build with `--output type=local`. Its Dockerfile sits outside the context, so the context's `.dockerignore` applies. The result must equal exactly the tracked allowlisted files, including the package data, with no planted fixture and nothing else.
3. **Build:** `docker compose … build api`, under a shell `timeout 900`. The job records the built image ID.
4. **`image`:** runs in `docker run --rm --network none --read-only --cap-drop ALL`. Checks:
   - the tag resolves to the recorded ID; UID and GID are 10001;
   - all three entry points answer `--help`;
   - the installed-package import and production-registry check;
   - the offline migration SQL;
   - `/app` contains only `alembic.ini`, uv is absent, and the runtime files are owned by root and not writable by the runtime user.
5. **`smoke`:**
   - **Database image:** pulls only `pgvector/pgvector:0.8.7-pg17@sha256:ac08538c…`, with a 300 s timeout.
   - **Startup:** `up -d --no-build --pull never --wait --wait-timeout 180`, with a 240 s timeout.
   - **Image identity:** `migrate`, `api` and `worker` must all run the recorded image ID.
   - **Account and key:** seeds the synthetic demo accounts and creates a key for the demo reviewer.
   - **Ingestion:** creates a vendor (201) and uploads synthetic Markdown (202), then polls the job every 2 s within a 90 s deadline until `succeeded`. The revision must be active with `ingestion_state` `active`, and the chunks verified complete; a duplicate upload returns 200.
   - **Worker stop:** stops the **idle** worker with `stop -t 60` and inspects the stopped container. It must have exited with code 0 and no OOM kill; code 137 (SIGKILL), worker code 5, or any other state fails.
6. **`cleanup`** (`if: always()`):
   - **Refusal:** the command refuses any selection that is not a CI project and tag pattern, or whose project and image tag name different runs or attempts.
   - **Ownership:** it lists the containers, volumes and networks carrying this project's Compose label and checks every listing's exit status. An unavailable inventory is never treated as empty: if any listing fails, the destructive `down` is refused and cleanup fails.
   - **Removal:** it runs `down -v --remove-orphans` (120 s), then verifies again. Cleanup reports `ok` only when that verification succeeds and shows nothing left. It removes only this run's image tag, found with `docker image ls`, which distinguishes an absent tag from an unavailable inventory.
   - **Failure precedence:** errors are reported separately, without hiding an earlier workflow failure.
   - **Limit:** losing the runner or a hard cancellation can prevent cleanup from completing.

### Privacy and failure handling

- **Key handling:** the generated key is held only in memory.
  - **Private output:** both `create-key` streams are private; the command's raw output is never printed, stored or uploaded, on success or failure.
  - **Protect first:** every key-shaped string (`egk_…`) in either stream is registered for redaction and service-log checks **before** the exit status or output format is checked (corrected in Prompt 99), so a failed or malformed run cannot leak a key it printed.
  - **Masking:** each such string is also registered with `::add-mask::`, the one line that carries it to the runner, as a workflow command. That masking is an additional layer; the primary control is redaction.
  - **Redaction:** it also replaces anything key-shaped that was never registered.
- **Redaction:**
  - command outputs and the last 200 lines of each service's logs are captured into memory and redacted before display;
  - they are displayed only when the smoke fails, and are not assumed to be privacy-safe JSON;
  - HTTP bodies and exception representations are never printed, only status codes, fixed fields and exception class names.
- **Service logs:** retrieving every service's logs is part of acceptance (corrected in Prompt 99).
  - **Unavailable logs:** a nonzero status, a timeout or any retrieval error fails an otherwise successful smoke. The key check is reported as not performed for those services, never as passed. An empty log from a successful command is accepted.
  - **Key in logs:** any occurrence of the key in captured service logs fails the smoke, on success and failure. It is reported as a service name and count only.
- **Timeouts:** every subprocess call and HTTP request has its own timeout (10 s for HTTP), in addition to the polling deadline.
- **Failure precedence:** the first failure decides the exit status. After an earlier failure, unavailable logs and other diagnostic errors are reported as secondary.

## Consequences and limits

- **Run locally (Windows, Prompts 98–99; historical):** the last full run reported `1363 passed, 205 skipped` (204 PostgreSQL skips and one POSIX-only signal skip), and the focused helper and file tests `103 passed`. It covered:
  - ruff and strict mypy, now including `infra/ci/container_ci.py`;
  - the database-independent suite, including `tests/test_container_ci.py` (the smoke, cleanup and configuration logic against fake subprocess and HTTP functions, plus real subprocess timeouts and a local HTTP server). It includes the Prompt 99 regressions for unavailable logs, credential protection and cleanup ownership, which fail against the Prompt 98 helper;
  - `tests/test_container_files.py`: Dockerfile invariants, Compose and CI wiring, and an *approximation* of Docker's ignore rules applied to the real tracked files and nested fixtures.
- **Verified in CI (`682101b`):** It was verified in CI on `feat/container-stack` at `682101b` (`682101b4f06d099b147b8d21734fa83f7f53637f`; [CI run 38769986459](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459), a push event, conclusion success). From job logs retrieved by the external reviewer:
- [Ubuntu](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962186): `1364 passed, 204 skipped in 27.63s`;
- [Windows](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962338): `1363 passed, 205 skipped in 39.61s`;
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542961580): `204 passed, 1364 deselected in 59.62s`;
- [container job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986459/job/116542962209):
  - `compose config: ok` and `context: ok (72 files; 19 planted fixtures excluded)`;
  - the application image built;
  - the image checks passed: UID and GID 10001, `--help` for `eg-api`, `eg-worker` and `eg-admin`, installed imports, offline migration SQL and runtime contents;
  - the stack started with the database healthy, the migration complete and the API healthy, and `migrate`, `api` and `worker` ran the CI-built image;
  - an API key was created and held in memory; the upload was accepted (202), the ingestion job succeeded, and the revision was active with 2 verified chunks;
  - a duplicate upload returned the existing revision (200), and the idle worker exited with code 0 and no OOM kill;
  - `smoke: ok` and `cleanup: ok`;
- the [full-history secret scan](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224) ([job](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/38769986224/job/116542954404)): 41 commits scanned, no leaks found.

The reviewer did not run the suite or Docker locally. Claude's anonymous API session saw only the job and step conclusions (all `success`, none skipped) and could not retrieve the logs.
- **What this establishes:** CI Compose verification is complete for this version; under the accepted specification, it can satisfy M3's Compose requirement alongside M3's other criteria. Local Compose remains unverified. The smoke shows the tested idle-worker shutdown, not a shutdown bound for an in-flight handler. Overall M3 acceptance remains pending a separate review. This is a development stack: no production readiness, benchmark or general security guarantee is claimed. The approved uv exception is unchanged.
- **Before CI (historical, Prompts 98–101):** the image build, the effective build-context check, the image checks, the Compose smoke and cleanup had not run anywhere until that CI run.
- **Scope of the smoke:** it stops an idle worker. It does not prove that an in-flight handler drains in a container (M3b's process-level tests cover draining), nor multi-worker behaviour.
- **Development only:** there is no TLS, no secrets management (the database credentials are disposable and public), no resource limits, no backups, no image signing or SBOM, no registry publication and no production deployment. The non-root, read-only and capability settings are sensible defaults, not a security certification.
- **Docker behaviour relied on** (from Docker's documentation):
  - **Exercised by the passing CI run at `682101b`:** `pull_policy: never` together with a `build` section; `up --no-build --pull never --wait`; `init`; `${VAR:-default}` interpolation; `.dockerignore` matching; `--output type=local` exporting a `FROM scratch` stage; and `stop_signal: SIGTERM` with a normal worker exit inside the grace period.
  - **Not exercised:** Docker's documented forced SIGKILL after `stop_grace_period` expires. The idle worker exited normally (code 0) within the grace period, so the SIGKILL path never ran. The 60 s grace period remains an external termination budget, with the shutdown limitations above unchanged.
