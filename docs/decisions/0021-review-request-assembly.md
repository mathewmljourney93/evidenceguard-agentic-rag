# ADR-0021: Review template, Planner, prompts and request assembly

- **Status:** **Implemented by Claude Code in Prompt 182, corrected in Prompt 183 (see
  [Prompt 183 corrections](#prompt-183-corrections)) and accepted at external review in Prompt
  184 for a local implementation commit only** (see
  [External review (Prompt 184)](#external-review-prompt-184)). Publication and merge are not
  authorized; Linux verification and current-version CI are pending (historical: until Prompt
  184 the implementation was staged and implementation acceptance was pending). No application path, handler, endpoint, setting or production
  registry uses M5c, so none of its controls operates in the application, and overall M5
  acceptance is pending. Implements the
  [accepted M5c specification](../plan.md#m5c-review-template-planner-prompts-and-request-assembly-specification-accepted-at-review-prompt-181-implementation-pending)
  (proposed in Prompt 179, revised in Prompt 180, accepted at external review in Prompt 181 with
  C1–C11 and the two-pass `parse_output` wording clarification), the third slice of the
  [accepted M5 sequence](../plan.md#m5-implementation-sequence-accepted-at-review-prompt-170).
- **Date:** 2026-10-21
- **Builds on:** [ADR-0019](0019-model-call-contracts.md) (`StructuredRequest`, `PromptRef`,
  `parse_output` and the scripted fake) and [ADR-0020](0020-provenance-validation.md)
  (`QuestionEvidence`, `VerifiedQuestion`, `ProvenanceRejection` and quote matching).

## Decision

M5c adds five modules and three packaged data files to `evidenceguard_agents`: fixed errors, a
packaged digest-pinned review template with a pure parser and pinned loaders, a deterministic
Planner, two versioned system prompts with pinned loaders, and request assembly that serializes
every untrusted string only inside JSON string values of a closed schema, binds the system text
to the pinned prompt digest, refuses oversize requests and builds repair requests by reassembly.
It adds no persistence, migration, review handler, endpoint, setting, production registry entry,
live provider, network code or dependency, and changes no M1–M5b contract or behaviour.

**What it establishes.** Structural safety of the request format (document text cannot end a
JSON string value or create a field), deterministic bytes and request digests, exact
template and prompt identity for artifacts loaded through the pinned loaders, and refusal instead
of truncation. **What it does not.** It does not make a live model injection-resistant (a model
can still follow persuasive document text; measured in M7), does not guarantee that a model
encodes a quotation correctly (a wrongly encoded one fails the existing M5a/M5b checks), cannot
prove that its evidence or Verifier inputs came from trusted paths (M5g's obligation), makes no
peak-memory or hard-deadline guarantee, and does not enforce the lifetime repair or call budget
(M5g). A request digest identifies content and configuration, not tenant authorization or review
identity.

## Modules, data and public contract

| File | Contents |
|---|---|
| `artifact_errors.py` | `ReviewArtifactError` and the nine fixed errors; `run_guarded` and `require` |
| `templates.py` | `TemplateRef`, `ReviewTemplate`, `parse_template`, `load_template`, `load_pinned_template`, the template registry |
| `planner.py` | `PlannedQuestion`, `plan_review` |
| `prompts.py` | `PromptSpec`, `load_prompt`, `load_pinned_prompt`, the prompt registry and the binding check |
| `assembly.py` | `VERIFIER_INPUT_FORMAT`, `ANALYST_INPUT_FORMAT`, `ModelSettings`, `VerifierRequestInputs`, `AnalystRequestInputs`, `RepairReason`, `assemble_verifier_request`, `assemble_analyst_request`, `assemble_repair_request` |
| `data/templates/vendor_security_review_v1.toml` | the accepted first template |
| `data/prompts/verifier/v1.md`, `data/prompts/risk_analyst/v1.md` | the v1 system prompts |

**Pinned artifacts** (SHA-256 of the exact file bytes; UTF-8 without BOM, LF, ASCII only):

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `vendor_security_review` v1 (template) | 1,969 | `26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a` |
| `verifier` v1 (purpose `verifier`) | 4,213 | `629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d` |
| `risk_analyst` v1 (purpose `risk_analyst`) | 4,002 | `f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29` |

The template holds exactly the accepted M5c-C2 table (eight questions, IDs and texts shared with
the evaluation questions, separately authored queries in the accepted order, explicit
documentary flags) under the title "Vendor security review", with a two-line comment header. The
prompts are new text written in Prompt 182 to the accepted content requirements (M5c-E): role and
task, the input format and the exact output schema, "Respond with one JSON object only", the
untrusted-data statements (every `evidence` string; for the Analyst every
`verification.rationale`, `claims[].text` and `citations[].quote`), chunk-ID and exact-quote
rules, single standard JSON escaping of quotes, `insufficient_evidence`, and no canary list or
injection claim. Since Prompt 183 the Verifier prompt states the accepted verdict mapping
(`supported` for an answer the cited passages give, affirmative or negative; `contradicted` only
for conflicting cited passages with at least two distinct quotations; `insufficient_evidence`
when the evidence does not answer), both prompts say that EvidenceGuard checks quote provenance
only, and both describe the optional `repair` member. **Their exact wording and bytes are part of
this implementation review.**

- **Values** are frozen dataclasses with validating keyword-only constructors (exact types,
  `bool` never an `int`, tuples only, unknown keywords rejected). Nested values are rebuilt
  through their own constructors (`PromptRef`, `RetrievalRequest`, `QuestionEvidence`, `VerifiedQuestion`,
  `ProvenanceRejection` and the M5c values), so `model_construct` and `object.__setattr__`
  bypasses are revalidated. A nested `EvidenceQuestion` in either stage's inputs is checked at
  the M5c boundary **before** any reconstruction (exact `str` ID and text, an exact `tuple` of
  exact `str` queries, an exact `bool` flag), then rebuilt with `EvidenceQuestion.model_validate`
  and required to be unchanged in value and type (Prompt 183). `dataclasses.replace` runs the
  same constructor. Representations
  show identifiers, versions, purposes, digests and counts only.
- **Template rules.** The template-string rule (exact `str`, strict UTF-8, no NUL, equal to its
  own `str.strip()`, bounded) applies identically to the title, question texts and queries; the
  template-question rule additionally requires the built `EvidenceQuestion` to equal the
  supplied fields exactly. `parse_template` takes exactly `bytes` (at most 65,536, no BOM, strict
  UTF-8, `tomllib`, closed keys at every level) and returns the SHA-256 of exactly those bytes.
- **Trusted loading.** `load_template` maps wrong argument shapes to `InvalidAgentArgumentError`,
  an unregistered pair to `UnknownTemplateError`, and a missing, unreadable, oversize, altered or
  invalid resource or a registry-key mismatch to `TemplateIntegrityError`.
  `load_pinned_template(ref)` additionally requires the complete loaded reference to equal `ref`.
  `load_prompt`/`load_pinned_prompt` do the same for prompts (`UnknownPromptError`,
  `PromptIntegrityError`; empty, BOM, NUL, non-UTF-8 and oversize bytes are each refused) and
  return the exact decoded text. A directly constructed `ReviewTemplate` never proves packaged
  origin; trusted paths use only the pinned loaders.
- **Bounded reads.** Resources are opened in binary mode through `importlib.resources.files` by
  fixed registered names and read with repeated `read(n)` calls. Each request is bounded by the
  remaining allowance (the limit plus one byte minus the bytes already received); short reads are
  continued; reading stops at end of file or once more than the limit has been received, so under
  the reader contract no more than the limit plus one byte is received. An oversize resource is
  refused. The file is never read whole and then measured.
- **Planner.** `plan_review(template, *, k=8)` returns one `PlannedQuestion` per question in
  template order with `RetrievalRequest(question.search_queries, k)`; `PlannedQuestion` requires
  the request's queries to equal the question's search queries exactly. No expansion or model
  call.
- **Prompt binding (M5c-E1).** Before serialization each assembler rebuilds the `PromptSpec` and
  settings, requires the function's purpose, a registered `(prompt_id, version)` of that purpose
  whose pinned digest equals the reference digest, and a 1–64,000-byte strict UTF-8 system text
  without NUL whose SHA-256 equals that digest. `StructuredRequest` is not relied on for this.
- **Assembly.** The closed `eg-verifier-input-v1` and `eg-analyst-input-v1` objects of M5c-F1 and
  F2 are built from rebuilt inputs (header and body separate, rank order, only validated
  citations, claims and rationale for the Analyst; no tenant, review, snapshot, revision or
  document ID or `document_key`), every string is checked for strict UTF-8 encodability
  (`InvalidAssemblyInputError` otherwise), and the object is serialized with
  `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
  allow_nan=False)`. A user text above 400,000 UTF-8 bytes, all metadata included, is
  `RequestTooLargeError` before any `StructuredRequest` exists; nothing is truncated. Replies are
  validated by M5a's unchanged two-pass `parse_output`; nothing decodes returned quotations again.
- **Repair (M5c-F5).** `assemble_repair_request(original, inputs, reason)` rebuilds all three,
  checks purpose and question, reassembles the unrepaired request from `inputs` and requires it
  to equal `original` in every field (so an already-repaired request is rejected), then adds
  `"repair":{"citation_index":…,"item_index":…,"reason":…}` and keeps every other field.
  `RepairReason` accepts `invalid_output` (no positions, either purpose) or an M5b
  `RejectionReason` under exactly the `ProvenanceRejection` stage and position rules.
- **Errors and process control.** Each public operation runs as one guarded operation: ordinary
  failures become a fresh fixed error (code as message) raised after the handler with no cause or
  context; process control propagates as the same object. Nothing logs.

## Implementation choices and deviations

Routine choices within the accepted contract:

1. **Error base and runner.** A `ReviewArtifactError` base class; `run_guarded(build, error,
   keep=…)` re-raises a kept M5c error class as a fresh instance of that class and maps every
   other ordinary failure to `error`. `artifact_errors.py` imports `collections.abc` and `typing`
   for these signatures (M5c-B lists no imports for this file).
2. **Shared private helpers.** `prompts` uses `templates._read_packaged`; `planner` uses
   `templates._rebuilt_template` and `_template_question`; `assembly` uses `prompts._is_bound` and
   `_rebuilt_spec`. The registries are private module dictionaries.
3. **Identifier checks without `re`.** The template-ID pattern is checked character by character
   so `templates.py` stays within its accepted standard-library list; question IDs use the
   existing `is_question_id`.
4. **`RepairReason` positions** are validated by constructing an M5b `ProvenanceRejection` with
   `rejected_count` 1 (valid for every reason), so the rules cannot drift from M5b.
5. **Nested question rebuild** for both stages uses the general boundary check of Prompt 183
   (exact field types, revalidation, unchanged values), not the template-question rule.
6. **Defaults** `DEFAULT_MAX_OUTPUT_TOKENS = 4_096` (C6) and the M5a `DEFAULT_TIMEOUT_MS`.

Implementation choices **approved at review (Prompt 183)** (listed as items needing review in
Prompt 182):

1. **Existing packaging test narrowed.** `test_m5b_is_not_wired_into_any_application_or_handler`
   asserted that no agents module mentions `provenance`. M5c-B places the import of
   `evidenceguard_domain.provenance` in `assembly.py`, so the test now exempts exactly that file;
   every other check is unchanged. The agents file-set test now lists the accepted M5c modules
   and `data/` directory.
2. **Bounded-read strategy.** Each request is bounded by the remaining allowance and no more
   than the limit plus one byte is accumulated. The earlier specification and docstring wording
   (the total *requested* never exceeds the limit plus one byte) did not hold for the sum of
   requests under short reads and was corrected in Prompt 183; the strategy itself is unchanged.
   The tests pin the per-request bound and that an oversize resource stops after exactly the
   limit plus one byte.
3. **Ground-truth separation test scope.** The test that the template copies no answer-bearing
   label compares anchors, gold and forbidden lists, acceptable claims and quotes, but excludes
   epoch names and `expected_status` values, because the status value `documentary_support` is
   also part of the template's own key `requires_documentary_support`. This is a limited check
   alongside the separately reviewed template table, not a universal proof against evaluation
   contamination.

No dependency, lockfile or `pyproject.toml` change was needed: the wheel and sdist include the
data files without an explicit include (build comparison below).

## Prompt 183 corrections

**Reviewer evidence (isolated, not project checks).** The external reviewer verified the Prompt 182
export's size and SHA-256, extracted the five modules and three resources (all eight Git blob
hashes and the three resource SHA-256 values matched), inspected the implementation, prompts,
tests, packaging and workflow changes and this ADR, and ran 27 isolated checks with Python
3.12.14, Pydantic 2.14.0 and published dependencies from `90295717`, using fixture helpers
extracted from the submitted test module without running its tests: 23 passed and 4 failed, plus
targeted observations of a serializer warning and the verdict mismatch below. The reviewer ran no
project suite, build, installed-wheel check, database, Docker or provider call.

**Finding A: nested questions were normalized.** Through the public entry points, a bypass-built
nested question with padded text, a `search_queries` list or `requires_documentary_support` set to
`1` was accepted and normalized on the Verifier path (M5b's `QuestionEvidence` reconstruction ran
before any M5c check and could emit a Pydantic serializer warning echoing a query), and the integer
flag was accepted on the Analyst path (its equality check does not distinguish `1` from `True`).
*Fix:* `assembly._checked_question` checks the supplied question's own fields with exact types
before any reconstruction, rebuilds through `EvidenceQuestion.model_validate` and requires every
field unchanged in value and type; the Verifier inputs check the nested question before
rebuilding `QuestionEvidence` (from the checked question) and recheck the stored one, and the
Analyst inputs use the same check. Assembly and repair rebuild the inputs, so they apply it too.
`EvidenceQuestion`, `QuestionEvidence`, M5a and M5b are unchanged.

**Finding B: the Verifier prompt contradicted the verdict mapping.** Rule 7 asked for
`contradicted` when passages "show that the answer is negative", whereas M5b derives
`verdict_unsupported` for `contradicted` with one distinct quotation and accepts a negative answer
under `supported`. *Fix:* the Verifier prompt now states the accepted mapping (see above), both
prompts state that provenance checks prove quote existence only, and both describe the optional
`repair` member (a fixed failure category and positions in the previous response's claims or
findings and their citations, not evidence ranks or input citation indexes; no previous response
is supplied). The unpublished v1 files were corrected in place.

**Changed pins.** `verifier` v1 `2201e3fa…e325` →
`629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d`; `risk_analyst` v1
`9f250b8e…84e6` → `f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29`; the pinned
Verifier, Analyst and repaired-Verifier request digests in the tests and the installed-wheel
request digest changed accordingly (recomputed independently with the standard library; the user
texts and their digests are unchanged). The template is unchanged.

**Regression comparison** (the new Finding A and verdict-mapping tests, run against isolated
package copies of the submitted staged tree and of the corrected tree placed first on
`PYTHONPATH`, with import locations printed by a test plugin): submitted **10 failed, 8 passed**;
corrected **18 passed**. Of the 10 failures, 7 genuinely reproduce Finding A (Verifier padded text,
list queries and integer flag, each through inputs and through assembly and repair, and the
Analyst integer flag) and 3 are new coverage (a `str`-subclass query on both Verifier paths and the
Analyst path). The 8 cases passing on both are controls (a `None` flag already refused, the
Analyst padded text and list already refused, valid bypass-built questions, process-control
identity) and the two verdict-mapping contract tests. The verdict-mapping and prompt-wording tests
are contract coverage; they do not show that the earlier prompt was executed by a model or that a
live model follows the corrected one.

## External review (Prompt 184)

**Decision.** The external reviewer accepted the corrected M5c implementation from Prompts
182–183 in Prompt 184 **for a local implementation commit only, pending Linux verification and
current-version CI**. The acceptance covers the five agents modules; the exact accepted template
and both corrected v1 prompt resources; pinned loading, bounded reads and deterministic planning;
prompt binding, the closed request schemas and deterministic serialization; strict nested-question
reconstruction and warning privacy; size refusal and reassembly-based repairs; the tests, packaging
changes and the additive installed-wheel workflow extension; and the three implementation choices
approved in Prompt 183. Publication and merge are not authorized by Prompt 184. M5d–M5h and
overall M5 acceptance are pending. None of the 308 integration tests has run against this
implementation version; M5c adds no PostgreSQL tests.

**Reviewer evidence and scope.** The reviewer independently verified the byte sizes and SHA-256
values of both exports (`.local/p182/m5c-implementation.diff`, 205,096 bytes,
`f0ff49b14ef6e956e754afc588ce2d1832320ea86fad556613ad42c266537381`;
`.local/p183/m5c-question-boundary-and-prompt-corrections.diff`, 78,465 bytes,
`6af16679af451c865b0d8167eff8bbf2c72702e0a3aeda1363f9db3b3324a16c`). The corrected code was
reconstructed by applying the Prompt 183 correction to the extracted Prompt 182 files; the eight
reconstructed changed-file blobs matched the correction export, including `assembly.py`
`67a1d6b987c8f1d4d645fb54dc7a75045e3d4c0c`, `prompts.py`
`1e646a1dc46eb4d8c4aa30e7edc2eadc9ddc8ed5`, `templates.py`
`dcd5341cdbb9235a6f64ce24a076af381329e0eb`, `tests/test_request_assembly.py`
`d5771de5f26573c488862622182c65cbb4aa0273` and `tests/test_prompts.py`
`9e0b425e207bb98ac30ffbfa6c669dfd53b35786` (Claude Code confirmed the same staged blobs). The
reviewer verified the packaged artifacts: template 1,969 bytes
`26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a`, Verifier prompt 4,213 bytes
`629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d` and Risk Analyst prompt 4,002
bytes `f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29`. **All 38 isolated
reviewer checks passed** with Python 3.12.14, Pydantic 2.14.0 and existing dependencies from
fixed baseline `90295717`: the original 27 checks with the corrected artifact and request pins and
11 additional checks. They covered packaged digests, planner behaviour, loader classifications,
prompt binding, pinned request digests, adversarial JSON round trips, invalid metadata Unicode,
both size boundaries, repair preservation and rejection, fixed resource errors, process-control
identity, all four previous nested-question failures, no warning from a malformed query, assembly
and repair revalidation for both stages, valid bypass-built controls, string-subclass query
rejection, supported negative answers, conflicting quotations, one-quotation rejection and the
revised prompt and repair wording. Fixture-building helpers were extracted from the submitted
test module without executing its pytest tests. These are isolated checks on reconstructed copies,
not execution of the project suite, the submitted pytest modules, a build, an installed wheel, a
database, Docker or a provider; the prompt checks and scripted contract paths do not establish
live-model behaviour.

**Claude Code's results (separately attributed).** The Prompt 183 Windows results below (the
corrected regression comparison 18 passed; the submitted comparison 10 failed and 8 passed, 7
failures reproducing Finding A and 3 new coverage; the three M5c modules 251 passed; the focused
command 989 passed; full suite `3427 passed, 310 skipped`; collection 308 integration and 3,429
non-integration tests; static checks, the offline build comparison, the installed-wheel step and
the direct installed-wheel boundary probe) remain historical local evidence, not exact-commit CI.

## Verification (Prompt 183, local Windows, Claude Code; historical local evidence)

Locked offline environment, no database URL configured.

- `ruff check .`: all checks passed; `ruff format --check .`: 201 files already formatted.
- Strict `mypy`: no issues in 159 source files.
- The three M5c test modules: **251 passed**.
- The focused twelve-file command recorded in Prompt 182: **989 passed**.
- Full suite: **3427 passed, 310 skipped**: 308 PostgreSQL tests (`EG_TEST_DATABASE_URL` not
  set), one symbolic-link test and one POSIX-only signal test. Collection: 308 integration and
  3,429 non-integration tests.
- Offline `uv build` compared with the preserved `09587126` baseline build: wheel 96 → 104
  members (the eight M5c files added; only `METADATA` and `RECORD` changed; nothing removed);
  sdist 199 → 211 (the M5c modules, data, three test modules and this ADR added; only `PKG-INFO`,
  `README.md` and `tests/test_packaging.py` changed; nothing removed); all 16 `sample_data` files
  byte-identical; packaged resources 1,969, 4,213 and 4,002 bytes with the pinned digests.
- The complete installed-wheel step extracted from `ci.yml`, in a fresh environment outside the
  checkout (locked requirements with hashes installed offline, the wheel with `--no-deps`): exit
  0, all eight lines including the M5c line with the new pinned request digest, modules and
  resources from `site-packages`.
- A direct installed-wheel probe of Finding A: the Verifier padded text, list queries and integer
  flag are refused by direct construction (`InvalidAgentValueError`) and by assembly and repair
  of already-constructed inputs (`InvalidAssemblyInputError`), and the Analyst integer flag by
  direct construction, all with no warning; ordinary and valid bypass-built questions are
  accepted with the pinned user-text digest.

Not run: Linux, CI, PostgreSQL, Docker, the container smoke, any provider, network or live model.

## Verification (Prompt 182, local Windows, Claude Code; historical)

Locked offline environment, no database URL configured.

- `uv run --locked --offline ruff check .`: all checks passed; `ruff format --check .`: 200 files
  already formatted.
- `uv run --locked --offline mypy` (strict, including the five new modules): no issues in 159
  source files.
- The three new modules (`tests/test_review_templates.py`, `tests/test_prompts.py`,
  `tests/test_request_assembly.py`): **230 passed**.
- Focused command (the three new modules plus `test_packaging`, `test_model_calls`,
  `test_agent_outputs`, `test_scripted_provider`, `test_provenance`, `test_quote_matching`,
  `test_retrieval_contracts` and `test_evidence`): **968 passed**.
- Full suite: **3406 passed, 310 skipped**: 308 PostgreSQL tests (`EG_TEST_DATABASE_URL` not
  set), one symbolic-link test and one POSIX-only signal test. Collection: 308 integration and
  3,408 non-integration tests (3,716 in total).
- Pinned values in the tests are literals computed independently (standard-library `hashlib` and
  `json` over hand-written expected texts and the M5a canonical form, and `sha256sum` over the
  files), not by calling the code under test.
- Offline `uv build` of the working tree compared with a `git archive` build of `09587126`:
  wheel 96 → 104 members (added the five modules and three data files with the pinned digests;
  changed only `RECORD` and `METADATA`, whose long description is the README; nothing removed);
  sdist 199 → 211 members (added the modules, data files, three test modules and this ADR;
  changed only `PKG-INFO`, `README.md` and `tests/test_packaging.py`; nothing removed); all 16
  `sample_data` files byte-identical.
- The complete installed-wheel step extracted from `.github/workflows/ci.yml` ran in a fresh
  environment outside the checkout (locked non-development requirements exported with hashes and
  installed offline with `--require-hashes`, the wheel installed with `--no-deps`), once for the
  first build and again for the wheel rebuilt from the final staged tree: exit 0 both times, all
  eight lines printed including "review template, prompts and request assembly ran from the
  installed wheel", with modules and resources imported from `site-packages`.

Not run: Linux, CI, PostgreSQL, Docker, the container smoke (which does not exercise M5c), any
provider, network or live model call.

## Limits and later-slice obligations

- Structural encoding only; no semantic injection resistance, live quality or prompt-quality
  claim. The canary acceptance fixture, negative control and authorized-quotation limitation
  probe remain M5g's; M5c tests only that the injected trust-center paragraph sits inside exactly
  one evidence string value.
- M5d stores the `TemplateRef`, both `PromptRef`s, the model settings and the tenant, review and
  snapshot bindings; M5e keys stored calls and outputs by request digest within those bindings;
  M5g loads artifacts only through `load_pinned_template` and `load_pinned_prompt`, supplies only
  trusted evidence and Verifier values, enforces the repair and call budget and runs the canary
  fixtures; M7 measures live behaviour.
- Published template and prompt files are immutable; any change is a new version file with a new
  pinned digest.
