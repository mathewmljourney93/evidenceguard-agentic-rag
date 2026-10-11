# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status: milestone M1a (pre-alpha)

**What works now:**
- One installable Python 3.12 package (`evidenceguard`), managed with uv, with a committed lockfile.
- A minimal FastAPI app with one endpoint: `GET /healthz` returns `{"status": "ok"}`. This is a **process-liveness** check only. It does not check databases or any other dependency, and it does not mean the product works.
- An `eg-api` command that serves the app with Uvicorn, plus FastAPI's generated OpenAPI docs at `/docs` and `/openapi.json`.
- Tests, Ruff and strict Mypy. A CI workflow is configured for Ubuntu and Windows but **has not yet run in GitHub Actions**.

**Still planned** (see [docs/plan.md](docs/plan.md)):
- The rest of M1: domain state machines, structured logging and redaction.
- Everything after it: authentication, tenancy, persistence, ingestion, retrieval, model providers, the review workflow, the approval gate and evaluation.

No retrieval, agent workflow, evaluation results, security guarantees or benchmarks are claimed. Any future results will be published with their committed inputs, configuration and the command that reproduces them.

## Development (Windows, PowerShell)

**Prerequisite:** [uv](https://docs.astral.sh/uv/) 0.13 or later. uv provides Python 3.12; the repository pins it in `.python-version`.

Set up:

```powershell
uv python install 3.12
uv sync --locked
```

Check:

```powershell
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked pytest
uv build
```

Run the API (Ctrl+C to stop):

```powershell
uv run --locked eg-api            # http://127.0.0.1:8000
uv run --locked eg-api --port 8765
```

Then open `http://127.0.0.1:8000/healthz` or `http://127.0.0.1:8000/docs`. The same commands work in a POSIX shell.

Packaging layout and the reasons behind it: [ADR-0001](docs/decisions/0001-packaging-and-layout.md).

## Engineering record

[prompts.md](prompts.md) records, verbatim and in order, every prompt given to the Claude Code implementation session, with a short note on each outcome. [CLAUDE.md](CLAUDE.md) holds the standing development rules.

## Secret scanning

A GitHub Actions workflow ([secret-scan.yml](.github/workflows/secret-scan.yml)) is configured to run [Gitleaks](https://github.com/gitleaks/gitleaks) v8.30.1 over the full Git history on every push and pull request. **It has not yet run in GitHub Actions.**

A CI scan runs only after code has reached GitHub, so it cannot stop a secret from being published. Scan locally before every commit and push.

### Install and check

On Windows, winget installs the official release binary at a pinned version:

```powershell
winget install --id Gitleaks.Gitleaks --exact --version 8.30.1
gitleaks version   # expect: 8.30.1
```

On other platforms, download a binary from the [v8.30.1 release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1), verify it against `gitleaks_8.30.1_checksums.txt`, then run `gitleaks version`.

### Before every commit (including the first)

1. Review what is staged:

   ```powershell
   git status
   git diff --cached --name-only
   git diff --cached
   ```

2. Scan the staged content:

   ```powershell
   gitleaks git --pre-commit --staged --redact --verbose .
   ```

A new repository with no commits has no history to scan, so a full-history scan cannot check it. Before the first commit, scan the staged content instead.

### Before pushing

Once commits exist, scan the whole local history:

```powershell
gitleaks git --redact --verbose .
```

### Limits

- `--redact` keeps detected values out of the terminal output.
- If Gitleaks reports a finding, remove the secret and rotate the credential. Do not allowlist it.
- Scanners match known patterns and cannot detect every secret or every piece of private data. A clean scan does not replace a human review of the staged diff.
