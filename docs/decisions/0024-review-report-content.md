# ADR-0024: Review report content and deterministic Markdown

- **Status:** implementation **accepted at external review in Prompt 211 for a local
  implementation commit only** ([external review](#external-review-prompt-211)). In Prompt 212
  all five required jobs passed at `3e58f650` on `feat/review-report-content`
  ([feature CI evidence](#feature-branch-ci-evidence-at-3e58f650-prompt-212)). The reviewer
  independently retrieved the job logs and accepted that evidence in Prompt 213, which
  authorizes gated main publication. M5f is **feature-CI verified but not merged**; main
  publication has not happened yet. The specification was
  accepted at external review in Prompt 208. OpenAI Codex implemented it in Prompt 209. Claude
  Code recovered that staged work read-only after the Codex chat response was lost, and in
  Prompt 210 [corrected the builder's evidence checks](#evidence-binding-correction-prompt-210-claude-code)
  after external review findings.
- **Specification:** [accepted M5f specification](../plan.md#m5f-report-content-and-renderer-specification-accepted-at-review-prompt-208-implementation-pending),
  F1–F12 and binding clarifications A/B; [implementation status](../plan.md#m5f-implementation-status-feature-ci-passed-at-3e58f650-prompt-212-not-merged).
- **Preceding evidence:** M5e is reviewed, verified in CI and on main at `14f510e`, within
  [ADR-0023's recorded scope](0023-review-stage-persistence.md). Earlier Claude Code work,
  historical local results and independent external-review observations retain their attribution.

## Decision and integrity

`evidenceguard_domain.report_content` owns immutable ReportBinding, ReportVerification,
ReportStage, ReportFindingRef, ReportQuestion, ReviewReportContent, ReportMode, fixed errors
and the canonical encoder/hash/strict decoder. `evidenceguard_agents.report` owns the pure
trusted-input builder, source-bound recheck and pinned Markdown renderer. Domain imports only
the standard library and existing domain contracts; agents imports only the standard library,
domain and template values. No loader, persistence, provider, worker/API or runtime registration.

The wrapper uses `evidenceguard.review-report-content.v1` and renderer contract
`evidenceguard.review-report-markdown.v1`. M1's `evidenceguard.report-content.v1` bytes,
Unicode encoding, hash and legacy approval meanings are unchanged. The wrapper embeds the
legacy object and its separately verified digest and uses its own approval digest. It binds
tenant/review/vendor/job, request/snapshot and configuration; includes ordered planned questions,
preserved Verification status/rationale/claims/citations/authenticity, stage outcomes/reasons,
findings/follow-ups and the contract-mode stamp derived solely from hashed fields.

The builder rebuilds exact nested inputs before coercion/serialization, checks identities,
template/plan/stage order and completeness, rechecks Verification against retained evidence
and Analysis against its owner with shared=(). For every committed Verification shape it
applies M5e's E7 evidence-state rule. Closed U4 retains no evidence. Every other shape
retains evidence on the review snapshot, with `result.k` equal to the configured
`retrieval_k`, from which the stage's evidence digest is recomputed (Prompt 210). Successful Verification survives unresolved
Analysis. The P11 documentary finding is generated deterministically even after Analysis
failure. Source request/content/evidence/dependency bindings and available pinned call settings
are checked; omitted source digests remain references, not structural proof of provenance.
The source-bound recheck rebuilds and compares canonical bytes, without enrichment.

## Validation, privacy and bounded failure

Nested exact types reject bool-as-int, subclasses, malformed questions and bypass-built nested
values before model normalization or serialization. M5c-derived distinct queries remain a
wrapper invariant; M5e itself does not independently require query uniqueness. Supplied values
do not prove genuinely pinned template origin or trusted database loading.

The codec enforces closed fields and explicit nulls, canonical UUIDs/enums/integers, nested
rebuilding, deterministic finding identities and exact P11 payload, full Analyst citation-value
equality, dependency/configuration/plan/legacy digests and unresolved projection. A lexical
scan precedes JSON parsing, enforcing ASCII, escaped-string syntax, integer spelling/magnitude,
depth/token budgets; parsing rejects duplicate keys. Canonical re-encoding equality precedes
expected wrapper-digest verification. Bare legacy and unsupported wrapper/renderer versions
are refused, never silently upgraded.

All report value repr/str methods are explicit and privacy-safe; nested content is never
delegated to a dataclass/model default representation. They expose only allowed metadata,
never titles/text, queries, quotes/evidence, rationale/claims, finding/follow-up content or
payload bytes. Explicit encoding/rendering still returns the deliberately requested content.
Ordinary errors are fresh fixed public classifications raised outside handlers, with no
original text/cause/context, warnings, output or logs. Process-control objects propagate by
identity. These are supported-input boundaries, not a hostile-process sandbox.

Limits: 200 total findings, 100 questions, existing per-question field/citation/follow-up bounds,
16,777,216 wrapper and legacy bytes, depth 16, 500,000 structural tokens, integer magnitude
2,147,483,647, and 33,554,432 Markdown bytes. Finding overflow refuses the entire report;
no truncation or dropped mandatory finding. Other caps likewise return no partial output.
These are engineering limits, not proved tight maxima or performance/quality guarantees.

## Renderer and presentation tradeoff

The pinned renderer consumes only freshly validated hash-covered content. It follows the
accepted heading/field order and emits every dynamic scalar as a labelled indented JSON
literal, with ASCII escapes and additional reversible escaping for HTML metacharacters.
Quotes round-trip exactly after one JSON decode. No string-supplied Markdown, raw HTML or
URL is emitted as active syntax in conforming CommonMark code blocks; no URL is fetched.
The tradeoff is plain literal presentation without natural prose or clickable evidence links.
No browser/CommonMark-parser test or arbitrary-viewer safety is claimed. Content integrity,
presentation handling and semantic injection resistance are separate claims.

## Implementation choices for external review

- No change to the accepted field schema, digest semantics, renderer emission order or caps
  is intended. The choices below were accepted at external review in Prompt 211.
- Shared internal M5f boundary/preflight helpers live in the domain module and are reused
  by the agents module; they are implementation details, not additional stable public APIs.
  Existing domain constructors still perform their established semantic validation.
- The renderer checks the running ASCII byte count before storing each emitted line,
  accounting for removal of the final empty line; no partial rendering escapes on overflow.
- Existing packaging file-set/no-use assertions gain only the report.py exception needed
  for the accepted pure M5b/M5e consumer. New AST checks prohibit loaders/runtime/I/O imports
  and calls. Existing production registry assertions remain intact.
- The additive CI assertion constructs synthetic committed U4/U3 trusted values offline,
  builds/decodes/hashes/renders the wrapper and checks independently authored wire bytes and
  a literal digest. It does not execute persistence, a provider or an application review path.

## Historical local verification (Prompt 209, OpenAI Codex)

**Historical local evidence, not exact-commit CI.** These are OpenAI Codex's local Windows
working-tree results for the Prompt 209 source, before the Prompt 210 correction. They come
from Python 3.12.15 and Pydantic 2.14.0, and are not current-version CI or PostgreSQL
execution:

| Check | Observed result |
| --- | --- |
| Locked offline Ruff format/lint | 226 files formatted; lint passed |
| Strict mypy | All 181 source files passed |
| Three new M5f modules | 70 passed |
| Focused M1/M5b–M5e/packaging contracts | 849 passed |
| Full suite | 4,039 passed, 387 skipped |
| Integration collection | 385 selected, 4,041 deselected; unchanged integration count |
| Non-integration collection | 4,041 selected, 385 deselected |
| Offline baseline/candidate sdist and wheel builds | Passed; comparison below |
| Complete installed-wheel step and direct probes | Passed outside checkout; offline only |

No test database is configured. The 385 PostgreSQL-marked cases were collected, not run;
local skips establish no database behaviour. M5f adds 70 pure cases and three packaging
checks, explaining the 73-case increase to 4,426 total collected cases. Other historical
platform/runtime skips remain. No Docker, provider call, network operation or CI run.

Expected canonical bytes come from test-owned dictionaries and standard-library JSON/hash
operations, with independent pinned wrapper/legacy digests. The exact Markdown specimen is
a test-owned declaration of labels/values and emission order, independent of the renderer.
The lexical tests exercise real depth/token limits before general JSON parsing; content,
legacy and rendering comparisons also exercise exact cap/cap-minus-one boundaries using
scaled caps. No tight maximal-size or performance proof is claimed.

Both builds used a git-archive baseline at `8e0173c1c9325ed1e4602aa32fd42b44bd4325ba`.
The candidate wheel adds only evidenceguard_domain/report_content.py and
evidenceguard_agents/report.py; existing
wheel payloads are byte-identical except generated METADATA/RECORD. The sdist adds the six
authorized files; existing changed members are README, test_packaging and derived PKG-INFO.
Nothing was removed; sample and pinned resource bytes remain unchanged. Detailed comparisons
and hashes are in the ignored Prompt 209 checkpoints.

The final tested wheel hash and exact final-source correspondence are recorded in the
Prompt 209 handoff and ignored artifact checkpoints.

The complete installed-wheel step was extracted from ci.yml and executed in a fresh external
virtual environment, with locked runtime dependencies exported with hashes and installed
from cache using --offline --require-hashes, and the wheel using --offline --no-deps.
Imports and pinned resources were verified from site-packages, with isolated Python outside
the checkout. The production registry and all ten existing behaviour lines passed, plus
`hash-covered review report built, strictly decoded and rendered offline from the installed wheel`.
Existing checks remain offline: migration SQL is not PostgreSQL execution, Recall is arithmetic,
Voyage is mocked and model calls are scripted. The container smoke was not repeated.

Direct isolated wheel probes exercised S1/U1, preserved Verification/P11, strict decode/hash,
reversible adversarial quotation, malformed-byte refusals and private representations. The
project's three saved Markdown examples (successful, unresolved Analysis with P11, adversarial)
were inspected as text for the accepted headings, order, stamp, literals and final newline.
No browser/CommonMark-parser test was performed. At Prompt 209, publication, implementation
acceptance and current-version CI were pending.

## Evidence-binding correction (Prompt 210, Claude Code)

The OpenAI Codex chat response for Prompt 209 was lost. Its saved handoff and implementation
export survived, and Claude Code verified both read-only before this correction. The Prompt
209 results above remain Codex's saved evidence. As recorded at recovery, no original Gitleaks
log survives. That scan result, and the link, table and history-fidelity checks, are backed
only by the saved handoff and outcome text.

**Reviewer findings (external, isolated).** The reviewer's fixture probes used Python 3.12.14,
Pydantic 2.14.1, unchanged dependencies from `14f510e` and the submitted modules (report.py
blob `0111cca7…`, report_content.py blob `27b07dc6…`). They were not a project-suite,
installed-wheel, PostgreSQL or CI run.

- **A.** A review rebuilt through validating constructors with `retrieval_k=1` and a
  recomputed request digest was accepted with retained evidence whose `result.k` was 8.
- **B.** A U4/U3 world with retained evidence was accepted, and so was a U1 refusal
  Verification with U3 Analysis and matching valid histories but no retained evidence.

These findings concern the builder's supported-input consistency boundary. They do not show
that the M5e loader, which already enforces E7 and `result.k`, produces such values.

**Correction.** Only `evidenceguard_agents/report.py` changed in production. For every
committed Verification shape, successful or unresolved:

- U4 must have no retained evidence.
- Every other shape (S1, U1, U2, U5, U6) must have retained evidence on the review snapshot,
  with `result.k == retrieval_k`, and with the stage's evidence digest equal to the one
  recomputed from that evidence.

The digest recomputation also keeps M5e's question and query-count checks. Call digests are
already bound to the stage digest by StageHistory. Refusals are the existing fixed
`InvalidReportInputError`. The accepted precedence is unchanged: malformed inputs, binding
mismatch, incomplete stages, stage/evidence/owner consistency, then finding conflicts and
limits. Discarded U4 evidence is never inferred. These checks show consistency only, not
database origin, retrieval execution or relevance. The specification is unchanged.

**Regression coverage.** Ten new builder cases cover the following:

- configured `k` versus retained `result.k` for S1, U1 and U5;
- U4 with retained evidence;
- S1, U1 and U5 (a no-call shape) without retained evidence, with unchanged valid histories;
- an unresolved digest mismatch;
- incomplete stages taking precedence over evidence checks;
- source-recheck refusals;
- quiet fixed errors, and process control propagating from the unresolved-path check.

Valid controls cover matching `k`, U4/U3 without evidence, and U1/U3 and U5/U3 with evidence.
Against an isolated exact copy of the submitted report.py, 7 of these cases failed with
"DID NOT RAISE". Those were the k cases for S1, U1 and U5, the U4 case, the U1 and U5
missing-evidence cases, and the quiet-refusal case. The other 19 builder cases passed. Those
19 are the 16 existing cases plus three new ones the submitted builder already refused or
ordered correctly: S1 without evidence, the digest mismatch, and incomplete precedence. All
26 cases passed against the corrected module.

**Historical local verification (Prompt 210, Claude Code).** These are historical local
evidence, not exact-commit CI: Claude Code's local Windows working-tree results for the
corrected source, the same implementation bytes later accepted in Prompt 211. They come from
Python 3.12.15 and Pydantic 2.14.0, and are not current-version CI or PostgreSQL execution:

| Check | Observed result |
| --- | --- |
| Locked offline Ruff format/lint | 226 files formatted; lint passed |
| Strict mypy | All 181 source files passed |
| Three M5f modules | 80 passed |
| Focused M1/M5b–M5e/packaging contracts | 849 passed |
| Full suite | 4,049 passed, 387 skipped |
| Integration collection | 385 selected, 4,051 deselected |
| Non-integration collection | 4,051 selected, 385 deselected |
| Offline baseline/candidate sdist and wheel builds | Passed; comparison below |
| Complete installed-wheel step and direct probes | Passed outside checkout; offline only |

- **Skips:** 385 skips are PostgreSQL cases with no test database configured; they were
  collected, not run. Two are platform skips (symbolic links; Windows SIGTERM). The ten new
  cases account for the increase to 4,436 collected cases.
- **Builds:** the rebuilt `8e0173c1` git-archive baseline is byte-identical to Prompt 209's
  preserved baseline. Against that baseline, the candidate wheel again adds only the two M5f
  modules and changes only generated METADATA/RECORD. Against Prompt 209's tested wheel, the
  only payload change is report.py; METADATA embeds the README. The sdist differs from Prompt
  209's only in the authorized files and PKG-INFO. Sample and pinned-resource bytes are
  unchanged.
- **Installed wheel:** the complete step from ci.yml ran in a fresh environment outside the
  checkout. Runtime dependencies were installed with `--offline --require-hashes` and the
  wheel with `--offline --no-deps`. All existing lines and the M5f report line passed.
- **Direct probes:** isolated probes passed matching-k controls (S1/U1 Analysis, U1/U3, U5/U3)
  and U4/U3 without evidence. They also confirmed the following refusals: `k=1` in build and
  recheck for S1, U1 and U5; U4 with evidence; S1, U1 and U5 without evidence; binding and
  incomplete-stage precedence; and process control propagating by identity.
- **Artifact hashes:** the final artifact hashes and their correspondence to the final staged
  source are in the Prompt 210 handoff and the ignored `.local/p210/` records.

## External review (Prompt 211)

**Scope.** The external reviewer accepted the corrected implementation within the accepted
M5f contract, for a **local implementation commit only**. Publication, merge, CI and M5g are
not authorized by this acceptance. Both Prompt 210 findings (configured `k` versus retained
`result.k`, and evidence presence versus the committed Verification state) are resolved.

**Approved implementation choices.** These are the choices listed under
[implementation choices](#implementation-choices-for-external-review):

- shared internal M5f boundary/preflight helpers;
- bounded line-by-line renderer accounting;
- narrowly scoped packaging exceptions for the pure report consumer;
- the additive offline installed-wheel fixture.

**Reviewer evidence (independent, isolated).** The reviewer did the following:

- verified the sizes, line counts and full SHA-256 values of the Prompt 209 implementation
  export and the Prompt 210 correction export;
- inspected the submitted implementation and the correction, and applied the correction to
  isolated review copies;
- confirmed that the corrected report.py and test_report_builder.py bytes match their exported
  Git blob IDs (`94d6b379…` and `2a7fc2d5…`);
- ran 25 isolated checks on Python 3.12.14 and Pydantic 2.14.1, which passed.

Those checks covered the following:

- configured-`k` mismatch, and missing retained evidence, for S1, U1 and U5, each through both
  build and source recheck;
- U4 with retained evidence, through build and source recheck;
- valid matching-`k` and U4/U3 controls;
- binding-mismatch and incomplete-stage precedence;
- fresh fixed errors without original cause or context;
- no warnings, stdout, stderr or log records;
- KeyboardInterrupt, SystemExit and GeneratorExit propagating by identity.

They were not a project-suite, installed-wheel, database, PostgreSQL or CI run.

**Attribution.** Each body of evidence stays separately attributed:

- OpenAI Codex: the Prompt 209 implementation and its local checks.
- Claude Code: the read-only recovery, the Prompt 210 correction and its local, build and
  installed-wheel checks, and the Prompt 211 acceptance documentation.
- The external reviewer: the isolated evidence above.

The recovery disclosures stand. The Codex chat response for Prompt 209 was lost, and no
original Prompt 209 Gitleaks log survives.

**Limitations.** Accepting the implementation bytes for a local commit does not cover:

- publication, merge, Linux verification or current-version CI;
- PostgreSQL: at Prompt 211 none of the 385 PostgreSQL tests had run against this version
  (see the Prompt 212 feature CI below), and M5f adds no PostgreSQL tests;
- an application review path: none uses M5f, and `run_review` remains unregistered;
- entailment, authenticity, semantic injection resistance or live-model quality, which
  provenance, structural and rendering checks cannot establish;
- a browser or CommonMark-parser check, or a tight maximal-size or performance proof.

## Feature-branch CI evidence at 3e58f650 (Prompt 212)

**Target.** Mathew pushed `feat/review-report-content` manually. Claude Code did not push.
After the push, the remote branch, local HEAD and upstream all equalled
`3e58f650afd79c4f54313ee083db23d85b9d1b6b`, and remote main stayed at `14f510e2`. That commit
is the history-only authorization commit (`docs: record M5f feature publication authorization`)
on top of the accepted implementation commit `6c1c9e9d`. Only prompts.md differs between them,
so every implementation, test, packaging and workflow blob is the accepted one.

**Claude Code's observations (public GitHub API, no credentials).** Both runs are for head SHA
`3e58f650…`, branch `feat/review-report-content`, event `push`, run attempt 1, observed between
05:00:48Z and 05:05:05Z on 2026-11-06:

| Run / job | Conclusion | Steps observed (all success) |
| --- | --- | --- |
| [ci 42165746043](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043) | success | — |
| [verify (ubuntu-24.04, Python 3.12)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717390) | success | formatting, lint, type-check, test, build distribution, install the wheel in a clean environment and import it |
| [verify (windows-2025, Python 3.12)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717245) | success | the same six steps as Ubuntu |
| [integration (ubuntu-24.04, PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717238) | success | initialize containers, confirm the database is ready, run integration tests, stop containers |
| [container (image build and Compose smoke)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717093) | success | validate Compose, verify build context, build and check image, Compose smoke test, clean up this run's Compose project and image |
| [secret-scan 42165746029](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746029) / [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746029/job/127721717133) | success | full-history checkout, checksum-verified install, scan Git history |

**Claude Code's log access (Prompt 212, historical).** The job-log API returned HTTP 403
without credentials, and the check runs carry no output text or annotations. Claude Code did
not change authentication, so it recorded no counts or output lines and inferred none from the
green conclusions. This remains an accurate record of Claude Code's own access at the time. It
is not a current claim that log evidence is unavailable, because the reviewer has since
retrieved the logs (below).

**Reviewer-retrieved logs (independent; recorded in Prompt 213).** The external reviewer
independently retrieved both runs, all five job conclusions and steps, and the complete job
logs. Both runs are for SHA `3e58f650afd79c4f54313ee083db23d85b9d1b6b`, branch
`feat/review-report-content`, event `push`, attempt 1, and completed successfully, with every
step of all five jobs succeeding. The reviewer also confirmed that the remote feature branch
was at `3e58f650` and remote main at `14f510e`, and that `3e58f650`'s parent is `6c1c9e9d`,
with prompts.md as its only changed file.

- [ci run 42165746043](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043):
  - [verify (ubuntu-24.04)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717390):
    `4051 passed, 385 skipped in 67.31s`.
  - [verify (windows-2025)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717245):
    `4050 passed, 386 skipped in 112.05s`.
  - **M5f module positions (both verify logs):** all 80 passed: test_report_builder.py 26,
    test_report_content.py 49 and test_report_renderer.py 5.
  - **Installed wheel (both verify logs):** each printed
    `production registry: ingest_revision, index_revision`, then all eleven behaviour lines.
    The first ten are the existing lines, from offline embedding/storage/indexing through the
    stage migration SQL line. The eleventh is the new
    `hash-covered review report built, strictly decoded and rendered offline from the installed wheel`.
  - [integration (PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717238):
    `collected 4436 items / 4051 deselected / 385 selected`, then
    `385 passed, 4051 deselected in 195.98s`.
    - Positions shown: the log shows 46 passing review-stage module positions and 28 passing
      review-creation module positions.
    - No individual test names: the log does not print them, so no named replacement test's
      individual result is claimed.
  - [container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746043/job/127721717093):
    the smoke and its cleanup succeeded. The smoke's own reported checks were:
    - a healthy database and API, and a completed migration;
    - migrate, API and worker all using the CI-built image;
    - the API key held in memory;
    - an upload accepted, ingestion succeeded, and an active revision with two verified chunks;
    - a duplicate upload returning the existing revision;
    - one offline indexing job enqueued, and a ready index with two embeddings;
    - the idle worker exiting with code 0;
    - `smoke: ok` and `cleanup: ok`.

    These are the smoke's own checks, not execution of an M5f application path.
- [secret-scan run 42165746029](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746029),
  [Gitleaks (full history)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42165746029/job/127721717133):
  92 commits scanned; no leaks found.

The PostgreSQL job ran the 385 integration cases at this SHA. M5f adds no PostgreSQL tests, so
this is regression evidence for M1–M5e persistence, not M5f database execution.

**Other evidence, separately attributed.**

- Claude Code: API conclusions and steps only.
- The reviewer: the logs above, and earlier, the 25 isolated checks.
- Historical local checks: Codex for Prompt 209, and Claude Code for Prompt 210 and the
  Prompt 211–212 documentation and preflight checks.

**Status.** The reviewer accepted this Prompt 212 feature evidence in Prompt 213. M5f is
**feature-CI verified at `3e58f650` but not merged**. Prompt 213 authorizes gated main
publication: committing this evidence, verifying it on the feature branch, a fast-forward and
Mathew's manual main push. Main publication has not happened yet. CI reruns and M5g are not
authorized. The container smoke does not exercise M5f. All the runtime limits below remain.

## Limits and handover

No M5f control operates in an application review path; run_review is unregistered. E7 still
requires a later additive output migration and reviewed atomic output-plus-job-success writer,
replay/completeness and worker composition in M5g, never an edit to 0007. M6 must review new
wrapper revision/approval/finalization contracts and approve/export its exact digest, not a
legacy digest. U4 discarded evidence, worker obligations, the accepted M3 lease window and
open M4d trusted-snapshot limitation remain. Offline wheel checks are packaging evidence:
offline migration assertions are not PostgreSQL execution, Recall is arithmetic, Voyage is
mocked and model calls are scripted. The container smoke does not exercise M5e/M5f. No live
provider or model-quality evidence exists, and no browser/CommonMark-parser or tight
maximal-size/performance proof is claimed. No entailment, authenticity, semantic injection
resistance or live-model-quality guarantee. The accepted canary/negative-control/limitation
contract remains unchanged for the later scripted end-to-end slice; no production blacklist.
M5g–M5h and overall M5 acceptance remain pending.
