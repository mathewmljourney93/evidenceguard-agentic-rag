# EvidenceGuard: Auditable Multi-Agent RAG for Vendor Risk Review

EvidenceGuard is a planned vendor-risk review copilot. It is intended to:

- ingest synthetic vendor documents for one tenant at a time;
- retrieve only evidence that tenant is authorized to see, with provenance;
- identify supported answers, contradictions and missing information;
- draft a report in which every claim cites its evidence;
- require a human to approve the exact draft revision before it can be finalized or exported.

It is evidence-based decision support, not legal advice or compliance certification.

## Status

**Planning and repository foundation only.** No application code exists yet. No retrieval, agent workflow, evaluation results, security guarantees or benchmarks are claimed. Any future results will be published together with their committed inputs, configuration and the command that reproduces them.

The planned stack is Python 3.12 with uv, FastAPI, PostgreSQL with pgvector, Anthropic Claude behind a typed provider interface, and a deterministic fake provider for tests and CI.

## Engineering record

[prompts.md](prompts.md) records, verbatim and in order, every prompt that directed this project, with a short note on each outcome. [CLAUDE.md](CLAUDE.md) holds the standing development rules.

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
