# ADR-0020: Provenance validation, quote matching and status derivation

- **Status:** **Implemented by Claude Code in Prompt 177, corrected in Prompt 178 (full citation
  values during analysis and its reload; see [Prompt 178 correction](#prompt-178-correction)) and
  accepted at external review in Prompt 179, pending exact-commit CI** (see
  [External review (Prompt 179)](#external-review-prompt-179)). Publication is authorized by
  Prompt 179 subject to the feature and main CI gates and had not run when this record was
  written. Overall M5 acceptance is pending; no review path uses M5b yet. Implements the
  [accepted M5b specification](../plan.md#m5b-provenance-and-status-derivation-specification-accepted-at-review-prompt-176-implementation-pending)
  (proposed in Prompt 174, corrected in Prompt 175, accepted at external review in Prompt 176 with
  the M5b-E1 input-identity clarification; P1–P16 are its implementation contract), the second
  slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
  Implementation review, Linux verification and current-version CI are pending.
- **Date:** 2026-10-20
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (`ChunkEvidence`, `RetrievalResult` and
  the value style) and [ADR-0019](0019-model-call-contracts.md) (`StructuredResult` and the strict
  Verifier and Risk Analyst output schemas).

## Decision

M5b adds one pure module, `evidenceguard_domain.provenance`, that turns a completed Verifier result
and the trusted retrieval evidence for one question into a `Verification` with derived status and
trusted citation metadata, restricts Risk Analyst findings to citations the Verifier already
validated, revalidates both on reload, and derives the deterministic documentary-support finding.
It has no persistence, migration, prompt, request assembly, orchestration, endpoint, setting,
provider call or production wiring, and changes no M1–M4 or M5a contract.

**What it proves.** An accepted citation proves **provenance only**: the stored quote is an exact,
contiguous substring of one span (header or body) of a chunk in the retrieval result supplied for
that question, with exact chunk-text and source offsets, and its tenant, revision, document,
source type and authenticity come from that trusted evidence. It does **not** prove semantic
entailment (whether the passage supports the claim; a model judgment measured in M7), document
authenticity (always `not_established`), or that the supplied retrieval result was really
retrieved for this review and question (M5d/M5g supply it from trusted paths). It makes no
injection-resistance claim: a genuine authorized quotation containing injected text is accepted.

## Module and public contract

`packages/domain/evidenceguard_domain/provenance.py` imports only the standard library
(`unicodedata`, `uuid`, `dataclasses`, `enum`, `contextlib`, `re`, `collections.abc`, `typing`)
and the domain modules `evidence`, `retrieval`, `model_calls`, `agent_outputs` and `chunks`. The
packaging tests pin this list and forbid network, file, environment, logging and direct Pydantic
imports, and check that no other package mentions the module (no wiring).

Public names, as specified (M5b-B): `MATCH_RULES` (`eg-quote-match-v1`), `QuoteSpanKind`,
`FindingKind`, `RejectionStage`, `RejectionReason`, the values `QuoteMatch`, `QuestionEvidence`,
`AcceptedCitation`, `ValidatedClaim`, `VerifiedQuestion`, `AnalyzedQuestion` and
`ProvenanceRejection`, the functions `match_quote`, `derive_status`, `verify_question`,
`recheck_verified`, `analyze_question`, `recheck_analyzed`, `documentary_gap_finding` and
`finding_id`, and the errors `InvalidProvenanceInputError` (`invalid_provenance_input`) and
`InvalidProvenanceValueError` (`invalid_provenance_value`).

- **Values** are frozen dataclasses with keyword-only constructors that check exact types (`bool`
  is not an `int`, tuples only, no `str` for a `UUID`), reject unknown keywords, rebuild every
  nested value through its constructor (`Citation`, `Verification`, `Finding` and
  `EvidenceQuestion` through `model_copy()`; `ChunkEvidence`, `RetrievalResult`,
  `StructuredResult` and the M5b values through their constructors) and enforce every
  constructor invariant of M5b-B1. `dataclasses.replace` revalidates. Representations show IDs,
  reasons, offsets, counts and digests only.
- **Quote matching** follows M5b-C exactly (segment-wise NFD, whitespace units, initial
  non-starter run as one segment, independent header and body spans, unit-boundary occurrences,
  first occurrence with no fallback, the 64-occurrence cap, the 1,000-code-point original bound,
  the edge-whitespace check, exact offset mapping). Span forms are computed at most once per chunk
  within one `verify_question` call.
- **Verifier conversion** binds the trusted `QuestionEvidence` and a revalidated completed
  Verifier `StructuredResult` for the same question, then runs the three phases of M5b-D with the
  M5b-F precedence and counts, deduplicates citations by `(chunk_id, original quote)` with
  canonical claim indexes, enforces P7 and the status table, and builds the `Verification`.
- **Analysis** checks owner, question, result and shared identities before examining any
  finding (M5b-E1), checks every finding, resolves each quote reference by whole-quote equivalence
  to an owner citation, requires every listed shared `Verification` to hold the **same full
  citation value** (else `citation_not_shared`; Prompt 178), enforces common verdicts, derives each
  finding's status from its own trusted citations, keeps follow-up questions verbatim and assigns
  deterministic IDs. A rejection never modifies the owner.
- **Reload.** `recheck_verified` rebuilds the value and evidence, requires matching identities and
  trusted metadata and recomputes `match_quote` from the trusted `ChunkEvidence` and the stored
  original quote, requiring a `QuoteMatch` equal in every field. `recheck_analyzed` rebuilds all
  inputs, checks the outer identities first (also for an empty analysis), then for every finding
  checks its scope, resolves each stored citation by `(chunk_id, quote)` to the trusted owner
  citation and requires **full `Citation` equality** (tenant, revision, chunk, source type, quote,
  authenticity) with it and with every listed shared Verification's citation (Prompt 178),
  re-derives the status from those trusted citations, and checks verdicts and IDs. Analyst and
  Verifier request digests are never compared.
- **Documentary rule (P11).** `documentary_gap_finding` checks the question identity first, then
  returns the fixed rule finding (ID `finding_id(…, documentary_support_required, 0)`, title
  "Documentary evidence required", the fixed statement, severity `medium`, status `missing`, the
  Verification's vendor citations) for a `vendor_claim` on a question requiring documentary
  support, otherwise `None`. **M5f and M5g must include it in the hash-covered report whenever
  its condition holds, even if analysis fails**; this module does not persist or render reports.
- **Errors and process control.** Every public operation runs as one guarded operation:
  ordinary exceptions (including nested `InvalidRetrievalRequestError`, `InvalidModelValueError`
  and Pydantic errors) become a fresh fixed error raised after the handler, with no cause or
  context; exception chains are never inspected; process control (`KeyboardInterrupt`,
  `SystemExit`, `GeneratorExit`) propagates as the same object. Model-caused failures never raise.
  Nothing logs.

## Implementation choices and deviations

Routine choices (resolved within the accepted contract):

1. **Internal-inconsistency signalling.** A private marker exception lets the shared guard report
   an unreachable failure while building the derived `Verification`, `AcceptedCitation`,
   `VerifiedQuestion`, `Finding` or `AnalyzedQuestion` as `InvalidProvenanceValueError`, while
   every other function failure is `InvalidProvenanceInputError` (pinned by a test that forces the
   `Verification` constructor to fail).
2. **Citation construction failure.** If building the `Citation` for an accepted original raised
   (not reachable for valid evidence), the reference is rejected as `quote_not_exact`, the same
   reason as a failed round-trip equality, rather than escaping as an error.
3. **Analyst quote resolution.** A reference resolves to the first owner citation with the same
   chunk ID and the same M5b-C quote form; for values produced by `verify_question` or accepted
   by `recheck_verified` that mapping is unique. A blank quote form never resolves
   (`citation_not_validated`).
4. **Bounds as named constants** (`MAX_QUOTE_CHARS`, `MAX_OCCURRENCES`, `MAX_SHARED_QUESTIONS` and
   others), the documentary-rule text as constants, and a `ProvenanceError` base class for the two
   fixed errors.

Implementation choices **approved at review (Prompt 178)** (originally listed as deviations
needing review in Prompt 177; each pinned by tests):

1. **`chunks` import.** The specification lists `evidence`, `retrieval`, `model_calls` and
   `agent_outputs`; the module also imports `evidenceguard_domain.chunks` for the existing
   4,000-code-point chunk bound (`MAX_CHUNK_CHARS`) instead of repeating the literal.
2. **`ProvenanceRejection.provenance_check`.** A read-only property returning the §4 value from
   the M5b-F table (`citation_rejected` for the reference, claim-coverage and the two citation
   reasons, otherwise `invalid_output`), so M5e/M5g need not re-encode the mapping.
3. **`rationale_blank` count.** The constructor accepts `rejected_count` 1 for `rationale_blank`
   (the table allows 1–2 for phase 3): by the precedence rule, `rationale_blank` is reported only
   when `verdict_unsupported` did not fail, so its count cannot be 2.

No specification conflict or impossibility was found. The Prompt 178 correction implements the
specification's requirement that Analyst findings cite only previously validated citations more
strictly than Prompt 177 did; it adds no new passage, normalization or matching behaviour.

## Unicode, trust and privacy limits

- **Segment-wise NFD is not canonical equivalence.** Canonically equivalent spellings can match
  differently. Pinned by tests: Tibetan U+0F40 U+0F74 U+0F73 and its full NFD U+0F40 U+0F71 U+0F72
  U+0F74 do not match each other in either direction; the quote U+AC00 is not found in the span
  U+AC01 but matches the first two units of the equivalent span U+1100 U+1161 U+11A8 (stored as
  U+1100 U+1161). An accepted quote is still always an exact contiguous original substring with
  exact offsets.
- **Unicode tables.** Results depend on the interpreter's `unicodedata`; a test pins Python 3.12
  and Unicode 15.0.0 (observed locally) and the maximum NFD expansion of 4 code points. Stored
  quotes are original substrings, so a table upgrade changes only future matches.
- **Trust.** Constructors and the recheck functions detect values inconsistent with the trusted
  values supplied; they do not prove which retrieval request originally ran, do not re-prove
  retrieval membership during analysis (owner and shared values must come from a trusted path that
  ran `verify_question` or `recheck_verified`), and give no protection against malicious trusted
  Python (`object.__setattr__`, `model_construct`, frame inspection) or direct database writes.
- **Privacy** covers public errors, rejections, representations and logs; explicit attribute
  access returns content by design.
- **Bounds** are the specified engineering defaults, not measured limits.

## Prompt 178 correction

**Finding (external reviewer).** The reviewer checksum-verified the Prompt 177 export
(`.local/p177/m5b-implementation.diff`, 196,163 bytes, SHA-256
`0c2846903ba2669a23939c65e369b91b4e3d9fd134f21935a8028465504cc030`), inspected the implementation
and relevant tests, and ran 17 isolated checks on the extracted submitted `provenance.py` with the
existing dependencies taken from `f04e0957`, Python 3.12.14, Pydantic 2.14.0, Unicode 15.0.0 and
fixture helpers extracted from the submitted tests. Fourteen passed; three failures reproduce one
defect: `recheck_analyzed` accepted a stored finding citation whose `document_revision_id` was
changed, whose `source_type` was changed together with a compatible changed `evidence_status`, or
both with `vendor_claim` changed to `documentary_support`. The reproduction used only ordinary
validated copies (`Citation.model_copy`, `Finding.model_copy`, `dataclasses.replace`); the owner
stayed valid and unchanged. The reviewer ran no project suite, build, wheel, database, Docker or
provider check; an attempted run of the two extracted pytest modules could not start because
pytest was unavailable in the review environment. These were isolated reviewer checks, separate
from Claude Code's project checks below.

**Cause.** `recheck_analyzed` checked membership by `(chunk_id, quote)` only and derived the status
from the stored finding's own citations, never requiring their full metadata to equal the trusted
owner's citations. `analyze_question` likewise checked shared membership by `(chunk_id, quote)`.

**Correction.** `recheck_analyzed` resolves every stored finding citation to the trusted owner
citation with the same `(chunk_id, quote)`, requires full `Citation` value equality (tenant,
revision, chunk, source type, quote, authenticity), requires that same value in every listed shared
Verification, and derives the expected status from those trusted citations; any difference is a
fresh `InvalidProvenanceInputError` with no cause or context. `analyze_question` requires the full
owner citation value in every listed shared Verification and otherwise rejects the finding with the
existing `citation_not_shared` (same precedence, positions and counts). The whole-quote matching
rule, the Unicode algorithm, request-digest rules, outer identity checks, valid empty analysis and
process-control behaviour are unchanged; no M1–M4 or M5a contract changed.

**Regression comparison (Claude Code).** Eight new tests in `tests/test_provenance.py` (selected
with `-k "analysis_reload or shared_citations_pass or shared_metadata"`) ran against isolated
ignored copies of the domain package under `.local/p178/` placed first on `PYTHONPATH`, one with
the submitted (Prompt 177) module and one with the corrected module; the import locations of
`provenance` and `evidence` were confirmed to be those copies before each run.

- *Corrected module:* 8 passed.
- *Submitted module:* 6 failed, 2 passed. **4 failures are genuine reproductions of the reviewer's
  defect** ("DID NOT RAISE"): the three reviewer cases (revision; source type plus status;
  revision, source type and status) and the combined case again with the error-field and
  unchanged-owner assertions. **2 failures are new consistency-policy coverage**, not
  reproductions of the reported reload defect: a shared Verification with the same chunk and quote
  but other metadata was accepted by analysis (expected `citation_not_shared`) and by reload.
  **2 controls passed** on both versions: the unaltered analysis reload and valid shared citations.

## External review (Prompt 179)

**Decision.** The external reviewer accepted the corrected M5b implementation (Prompts 177-178)
in Prompt 179, **pending exact-commit CI**, and authorized a local commit, publication of
`feat/provenance-validation` and, only after all five required jobs pass for that exact commit, a
fast-forward of `main`. Overall M5 acceptance is pending.

**Reviewer evidence and scope.** The reviewer independently verified the byte sizes and checksums
of both attached exports (`.local/p177/m5b-implementation.diff`, 196,163 bytes, SHA-256
`0c2846903ba2669a23939c65e369b91b4e3d9fd134f21935a8028465504cc030`;
`.local/p178/m5b-analysis-reload-correction.diff`, 45,918 bytes, SHA-256
`28d1c0557f5b570442d6f9a2f17e60beb3ca5d9ac67f4a1ff4ddaf0b4d1d0d77`) and inspected them. The
corrected source was reconstructed by applying the attached correction to the extracted submitted
source; its Git blob hash `23f941dcd0eb1542fe5a3a8aef6edd896e01585c` matched (Claude Code confirmed
the staged module has the same blob). The original 17 isolated checks were rerun against the
corrected module, and three more covered valid shared analysis and reload and the rejection of
inconsistent shared metadata during analysis and reload: **all 20 passed**, with Python 3.12.14,
Pydantic 2.14.0, Unicode 15.0.0 and existing dependencies from fixed baseline `f04e0957`. These were
isolated reviewer checks, not a project suite, build, installed-wheel, PostgreSQL, Docker or
provider run. Claude Code's Prompt 178 Windows results below remain separately attributed and are
not exact-commit CI.

## Verification (Prompt 178, local Windows, Claude Code; historical)

In the existing locked environment, offline, with no database URL set and no dependency, lockfile
or `pyproject.toml` change; Windows only, Linux and CI have not run.

- Regression comparison as above (corrected 8 passed; submitted 6 failed, 2 passed).
- `uv run --locked --offline ruff check .`: all checks passed.
  `uv run --locked --offline ruff format --check .`: 190 files already formatted (the count includes
  Markdown files; it is one higher than in Prompt 177 because ADR-0020 now exists).
  `uv run --locked --offline mypy` (strict): no issues in 151 source files.
- `uv run --locked --offline pytest -q -p no:cacheprovider tests/test_quote_matching.py
  tests/test_provenance.py`: 230 passed.
- Focused: `uv run --locked --offline pytest -q -p no:cacheprovider tests/test_quote_matching.py
  tests/test_provenance.py tests/test_packaging.py tests/test_model_calls.py
  tests/test_agent_outputs.py tests/test_scripted_provider.py tests/test_evidence.py
  tests/test_report_hashing.py tests/test_retrieval_contracts.py`: 742 passed.
- Full suite `uv run --locked --offline pytest -q -p no:cacheprovider -rs`: `3168 passed, 310
  skipped` (308 PostgreSQL integration tests without a database, the symbolic-link corpus test and
  the POSIX-only signal test). Collection: 308 integration and 3,170 non-integration tests.
- `uv build --offline` compared with the preserved Prompt 177 baseline build of `f04e0957` (not
  rebuilt): the same authorized differences as in Prompt 177 (wheel adds only `provenance.py`, with
  `METADATA` and `RECORD`; sdist adds the module, the two test modules and this ADR and changes
  `tests/test_packaging.py`, `README.md`, ADR-0019 and `PKG-INFO`); the 16 `sample_data` files are
  byte-identical; the wheel's `provenance.py` equals the corrected source.
- The extracted installed-wheel step (offline, locked requirements with `--require-hashes`, the
  wheel with `--no-deps`, fresh environment outside the checkout) printed all seven expected lines.
  A direct probe against that installed wheel, with `provenance`, `evidence` and `retrieval`
  imported from `site-packages`, accepted the unaltered analysis on reload and rejected the
  revision, source-type and status escalation with a fresh `InvalidProvenanceInputError`.

## Verification (Prompt 177, local Windows, Claude Code; historical)

All in the existing locked environment, offline, with no database URL set and no dependency,
lockfile or `pyproject.toml` change. Windows only; Linux and CI have not run.

- `uv run --locked --offline ruff check .`: all checks passed.
  `uv run --locked --offline ruff format --check .`: 189 files already formatted.
  `uv run --locked --offline mypy` (strict): no issues in 151 source files.
- New modules: `uv run --locked --offline pytest -q -p no:cacheprovider tests/test_quote_matching.py
  tests/test_provenance.py`: 222 passed (84 and 138).
- Focused: `uv run --locked --offline pytest -q -p no:cacheprovider tests/test_quote_matching.py
  tests/test_provenance.py tests/test_packaging.py tests/test_model_calls.py
  tests/test_agent_outputs.py tests/test_scripted_provider.py tests/test_evidence.py
  tests/test_report_hashing.py tests/test_retrieval_contracts.py`: 734 passed.
- Full suite `uv run --locked --offline pytest -q -p no:cacheprovider -rs`: `3160 passed, 310
  skipped`. The skips are the 308 PostgreSQL integration tests (no test database configured), the
  existing symbolic-link corpus test this Windows user cannot run and the existing POSIX-only
  signal test. Collection: 308 integration and 3,162 non-integration tests (224 new, all
  database-independent; M5b adds no PostgreSQL tests).
- Test-strength probe (local only, module restored byte-identically afterwards, SHA-256 checked):
  five deliberate mutations of the module (splitting the initial non-starter run, skipping P7,
  skipping the reload recomputation, selecting the last occurrence, unbinding the Analyst result
  question) each made the new tests fail (1, 3, 5, 5 and 2 failures).
- `uv build --offline` of the working tree and of `f04e0957` (from `git archive`): the wheel gains
  exactly `evidenceguard_domain/provenance.py` (its `RECORD` changes accordingly, and `METADATA`
  carries the updated README); the sdist gains the module, the two new test modules and this ADR,
  and changes `tests/test_packaging.py`, `README.md`, ADR-0019 and `PKG-INFO` (the plan and threat
  model are not in the sdist); nothing is removed; the 16 `sample_data` files are byte-identical.
- Installed wheel: the CI wheel step was extracted from `ci.yml` and run in a fresh environment
  outside the checkout, with its two install lines replaced by offline equivalents (locked
  requirements exported with hashes and installed with `--require-hashes`, then the built wheel
  with `--no-deps`). Every existing check and the new M5b check passed with imports from
  `site-packages`, printing "provenance matched a quote and derived a status from the installed
  wheel".

Not run: Linux, CI, PostgreSQL, Docker, the container smoke (which does not exercise M5b), any
provider or network call.

## Pending

Implementation review, Linux verification, current-version CI (including the installed-wheel step
on both platforms), publication, and the later slices that use these values: M5c (safe prompt
encoding and request assembly, including any decoding of encoded quotes before matching), M5d
(persisted snapshot trust), M5e (stage persistence, reloading through the constructors and recheck
functions), M5f (the hash-covered report representation, global report bounds with no silent
truncation, and mandatory inclusion of the documentary rule finding), M5g (orchestration, repair
and job precedence) and M5h (the model adapter). Overall M5 acceptance is pending.
