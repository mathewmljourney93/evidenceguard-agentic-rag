# ADR-0024: Review report content and deterministic Markdown

- **Status:** implementation **accepted at external review in Prompt 211 for a local
  implementation commit only** ([external review](#external-review-prompt-211)). Publication,
  merge, Linux verification and current-version CI remain pending. The specification was
  accepted at external review in Prompt 208. OpenAI Codex implemented it in Prompt 209. Claude
  Code recovered that staged work read-only after the Codex chat response was lost, and in
  Prompt 210 [corrected the builder's evidence checks](#evidence-binding-correction-prompt-210-claude-code)
  after external review findings.
- **Specification:** [accepted M5f specification](../plan.md#m5f-report-content-and-renderer-specification-accepted-at-review-prompt-208-implementation-pending),
  F1–F12 and binding clarifications A/B; [implementation status](../plan.md#m5f-implementation-status-accepted-for-a-local-commit-prompt-211-ci-pending).
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
- PostgreSQL: none of the 385 PostgreSQL tests has run against this version, and M5f adds no
  PostgreSQL tests;
- an application review path: none uses M5f, and `run_review` remains unregistered;
- entailment, authenticity, semantic injection resistance or live-model quality, which
  provenance, structural and rendering checks cannot establish;
- a browser or CommonMark-parser check, or a tight maximal-size or performance proof.

## Limits and handover

No M5f control operates in an application review path; run_review is unregistered. E7 still
requires a later additive output migration and reviewed atomic output-plus-job-success writer,
replay/completeness and worker composition in M5g, never an edit to 0007. M6 must review new
wrapper revision/approval/finalization contracts and approve/export its exact digest, not a
legacy digest. U4 discarded evidence, worker obligations, the accepted M3 lease window and
open M4d trusted-snapshot limitation remain. Offline wheel checks are packaging evidence;
the container smoke does not exercise M5e/M5f. No entailment, authenticity, semantic injection
resistance or live-model-quality guarantee. The accepted canary/negative-control/limitation
contract remains unchanged for the later scripted end-to-end slice; no production blacklist.
M5g–M5h and overall M5 acceptance remain pending.
