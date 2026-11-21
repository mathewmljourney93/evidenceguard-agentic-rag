"""Composition root of ``eg-eval`` (M7, ADR-0029): database, seeding and review execution.

``main`` is the installed ``eg-eval`` command; it hands ``run_suite`` to the pure argument parser
in ``evidenceguard_evaluation.cli``. Everything here runs in one process: no API or worker
service is started and no HTTP request is made to this application.

**Database.** Only ``EG_EVAL_DATABASE_URL`` is read. Its database name must end in ``_eval``,
must not be ``EG_DATABASE_URL``'s database, and its ``public`` schema must hold no table;
otherwise exit 3. This command never drops anything. It then applies the migrations and loads
the fixed corpus under ``sample_data/`` of the source tree (no corpus option) through the M4e
loader ``run_fresh_two_epoch``.

**Reviews.** For each (tenant, vendor) pair with labelled questions, a review is created with
the pinned template and prompts (the same loaders as the review API), the hash embedding
identity and an idempotency key ``eval-{run_id}-{n}-{pair}``. It is drained in-process with the
worker runtime's single-claim loop over a registry that holds only the production review
handler (``review_wiring.build_review_handler``) for this provider. The stored output, status,
call rows and retrieved sets are then read back, and the other tenant's reviewer must get
"not found" for both the review and its output.

**Suites.** ``contract`` runs the scripted fake in a refusal phase and a scripted phase per pair
(``evidenceguard_evaluation.contract``); its record says it is NOT a quality measurement.
``live`` refuses before anything is called unless the owner's files allow it: a zero total cap
(the committed value) is exit 4 first; then the selection must be confirmed and name the model,
prices and their date must exist, ``EG_ANTHROPIC_API_KEY`` must be valid and the working tree
clean outside ``docs/evaluation/runs`` (exit 3); then the worst-case ceiling must fit (exit 4).
Live calls go through ``BudgetGuard``. Tests reach the live path only with an injected fake
transport.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_agents.anthropic import AnthropicError, AnthropicProvider, AnthropicTransport
from evidenceguard_agents.prompts import load_prompt
from evidenceguard_agents.providers import ModelProvider
from evidenceguard_agents.templates import load_template
from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.jobs import TERMINAL_STATUSES
from evidenceguard_domain.reviews import (
    REVIEW_JOB_KIND,
    ReviewConfiguration,
    ReviewNotFoundError,
    ReviewRequest,
)
from evidenceguard_evaluation import budget as budget_rules
from evidenceguard_evaluation import cli, contract
from evidenceguard_evaluation.config import (
    EXIT_CONFIGURATION,
    EXIT_HARD_FAILURE,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_STOPPED,
    EvaluationRefusal,
    Selection,
    parse_selection,
    refuse,
    require_live_selection,
)
from evidenceguard_evaluation.pricing import ModelPrice, Pricing, parse_pricing
from evidenceguard_evaluation.records import (
    ObservedCall,
    ObservedCitation,
    ObservedClaim,
    ObservedQuestion,
    ObservedReview,
    RetrievedItem,
    RunContext,
    build_record,
    committed_cost,
    parse_record,
    record_bytes,
)
from evidenceguard_persistence.db import create_session_factory
from evidenceguard_persistence.migration_config import alembic_config
from evidenceguard_persistence.models import Chunk, Job, ReviewOutputRow
from evidenceguard_persistence.models import ReviewQuestionEvidence as EvidenceRow
from evidenceguard_persistence.models import ReviewStageCall as CallRow
from evidenceguard_persistence.review_outputs import load_review_output, load_review_status
from evidenceguard_persistence.reviews import create_review, load_review
from evidenceguard_persistence.safety import require_disposable_database
from evidenceguard_persistence.settings import (
    DATABASE_URL_ENV,
    DatabaseConfigurationError,
    ReviewConfigurationError,
    load_anthropic_settings,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY
from evidenceguard_retrieval.evaluation.corpus import FINAL, INJECTED, Suite, vendors_with_questions
from evidenceguard_retrieval.evaluation.recall import corpus_digest
from evidenceguard_worker.anthropic_http import HttpsAnthropicTransport
from evidenceguard_worker.evaluation import (
    TwoEpochState,
    _actor,
    load_suite,
    run_fresh_two_epoch,
)
from evidenceguard_worker.registry import HandlerRegistry
from evidenceguard_worker.review_wiring import build_review_handler
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

EVAL_DATABASE_URL_ENV = "EG_EVAL_DATABASE_URL"
EVAL_DATABASE_SUFFIX = "_eval"
TEMPLATE = ("vendor_security_review", 1)
WORKER_ID = "eg-eval"
ROOT = Path(__file__).resolve().parents[3]
TIMINGS = Timings(idle_poll=0.05, backoff_initial=0.05, backoff_cap=0.5, stop_check=0.05)
POLL_SECONDS = 0.05
CONTRACT_TRAPS: Mapping[tuple[str, str], Mapping[str, str]] = {
    ("halverson-freight", "ferrowick-payroll"): {
        "RET-01": contract.TRAP_FOREIGN_CITATION,
        "ENC-01": contract.TRAP_QUOTE_MISMATCH,
        "CMP-01": contract.TRAP_WRONG_MODEL,
        "CMP-02": contract.TRAP_INVALID_JSON,
    }
}
"""The fixed traps, on questions the ground truth leaves unlabelled for that pair."""
FOREIGN_TRAP_SOURCE = ("marisol-clinics", "lumenvale-cloud", "security-overview", 1)

TransportFactory = Callable[[SecretStr], AnthropicTransport]
GitRunner = Callable[[Sequence[str]], str | None]


class _Stopped(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- configuration -----------------------------------------------------------------------------


def review_configuration(model_id: str) -> ReviewConfiguration:
    """The pinned template and prompts with ``model_id``: the same loaders and defaults as the
    review API, so an evaluated review has the configuration digest a production one would."""
    template = load_template(*TEMPLATE)
    verifier, _ = load_prompt("verifier", 1)
    analyst, _ = load_prompt("risk_analyst", 1)
    return ReviewConfiguration(
        template_id=template.ref.template_id,
        template_version=template.ref.version,
        template_sha256=template.ref.sha256,
        verifier_prompt=verifier.ref,
        analyst_prompt=analyst.ref,
        model_id=model_id,
    )


def _git(arguments: Sequence[str]) -> str | None:
    """A fixed-argv ``git`` command in the source tree (no shell); ``None`` on any failure."""
    try:
        done = subprocess.run(
            ["git", "-C", str(ROOT), *arguments],
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", errors="replace")


def _git_sha(git: GitRunner) -> str:
    out = git(["rev-parse", "HEAD"])
    value = (out or "").strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else "unknown"


def require_clean_tree(git: GitRunner) -> None:
    """Live runs need a clean working tree outside ``docs/evaluation/runs`` (exit 3)."""
    out = git(["status", "--porcelain=v1", "--untracked-files=all"])
    if out is None:
        raise refuse("git status is unavailable; live runs need a git checkout")
    allowed = cli.RUNS_DIRECTORY.as_posix() + "/"
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if line.strip() and not path.startswith(allowed):
            raise refuse("the working tree has changes outside docs/evaluation/runs")


# --- the database -------------------------------------------------------------------------------


def eval_database_url(environ: Mapping[str, str]) -> URL:
    """The guarded evaluation URL, or ``EvaluationRefusal`` (exit 3) naming variables only."""
    try:
        return require_disposable_database(
            environ.get(EVAL_DATABASE_URL_ENV),
            environ.get(DATABASE_URL_ENV),
            EVAL_DATABASE_URL_ENV,
            EVAL_DATABASE_SUFFIX,
        )
    except DatabaseConfigurationError as error:
        message = str(error)
    raise refuse(message)


def _engine(url: URL) -> Engine:
    return create_engine(url, poolclass=NullPool, hide_parameters=True)


def require_empty_database(engine: Engine) -> None:
    """The ``public`` schema must hold no table (exit 3); nothing is ever dropped here."""
    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
        ).scalar_one()
    if count:
        raise refuse(f"the {EVAL_DATABASE_URL_ENV} database is not empty")


def _prepare(url: URL, suite: Suite) -> tuple[Engine, sessionmaker[Session], TwoEpochState]:
    engine = _engine(url)
    require_empty_database(engine)
    command.upgrade(alembic_config(database_url=url), "head")
    factory = create_session_factory(engine)
    return engine, factory, run_fresh_two_epoch(factory, suite)


# --- one review ---------------------------------------------------------------------------------


@dataclass
class _Run:
    """The state of one invocation."""

    factory: sessionmaker[Session]
    suite: Suite
    state: TwoEpochState
    run_id: str
    deadline: float
    clock: Callable[[], float] = time.monotonic
    chunk_cache: dict[Any, list[tuple[Any, int, str]]] = field(default_factory=dict)

    def check_deadline(self) -> None:
        if self.clock() > self.deadline:
            raise _Stopped("deadline_stopped")

    def job_status(self, job_id: uuid.UUID) -> str:
        with self.factory() as session:
            status: str = session.execute(select(Job.status).where(Job.id == job_id)).scalar_one()
        return status

    def drain(self, provider: ModelProvider, job_id: uuid.UUID) -> str:
        registry = HandlerRegistry(
            [(REVIEW_JOB_KIND, build_review_handler(provider, self.factory))]
        )
        while True:
            result = run_worker(
                DatabaseJobStore(self.factory),
                registry,
                worker_id=WORKER_ID,
                timings=TIMINGS,
                once=True,
            )
            status = self.job_status(job_id)
            if status in TERMINAL_STATUSES:
                return status
            if result.exit_code != 0:
                raise RuntimeError("worker_stopped")
            self.check_deadline()
            time.sleep(POLL_SECONDS)

    def chunks(self, tenant: str, vendor: str, document: str, n: int) -> list[tuple[Any, int, str]]:
        key = (tenant, vendor, document, n)
        if key not in self.chunk_cache:
            revision = next(
                loaded
                for ref, loaded in self.state.loaded.revisions.items()
                if (ref.tenant, ref.vendor, ref.document, ref.n) == key
            )
            with self.factory() as session:
                rows = session.execute(
                    select(Chunk.id, Chunk.ordinal, Chunk.text)
                    .where(
                        Chunk.tenant_id == revision.tenant_id,
                        Chunk.revision_id == revision.revision_id,
                    )
                    .order_by(Chunk.ordinal)
                ).all()
            self.chunk_cache[key] = [(row.id, row.ordinal, row.text) for row in rows]
        return self.chunk_cache[key]

    def tenant_chunk_ids(self, tenant_id: uuid.UUID) -> set[str]:
        with self.factory() as session:
            return {
                str(value)
                for value in session.execute(
                    select(Chunk.id).where(Chunk.tenant_id == tenant_id)
                ).scalars()
            }


def _other_tenant(suite: Suite, tenant: str) -> str:
    return next(t.slug for t in suite.corpus.tenants if t.slug != tenant)


def _anchors(suite: Suite) -> dict[str, str]:
    return {str(ref): anchor.quote for ref, anchor in suite.anchors.items()}


def _tenant_canaries(suite: Suite, tenant: str) -> tuple[str, ...]:
    """The other tenant's canary anchors: their text must never appear in this tenant's output."""
    return tuple(
        sorted(
            anchor.quote
            for ref, anchor in suite.anchors.items()
            if ref.revision.tenant != tenant and ref.anchor.startswith("canary")
        )
    )


def injected_markers(clean: Suite, injected: Suite) -> tuple[str, ...]:
    """The paragraphs the injected variant inserts, and each one's leading clause."""
    markers: set[str] = set()
    for ref in injected.corpus.injected:
        before = set(clean.texts[ref].split("\n\n"))
        for paragraph in injected.texts[ref].split("\n\n"):
            if paragraph not in before and paragraph.strip():
                markers.add(paragraph.strip())
                markers.add(paragraph.strip().split(":", 1)[0])
    return tuple(sorted(markers))


def _evidence(
    run: _Run, actor: ActorContext, review_id: uuid.UUID, vendor: str
) -> dict[str, tuple[RetrievedItem, ...]]:
    with run.factory() as session:
        rows = session.execute(
            select(EvidenceRow.question_id, EvidenceRow.evidence_canonical).where(
                EvidenceRow.tenant_id == actor.tenant_id, EvidenceRow.review_id == review_id
            )
        ).all()
    found: dict[str, tuple[RetrievedItem, ...]] = {}
    for row in rows:
        items = []
        for item in json.loads(row.evidence_canonical)["items"]:
            evidence = item["evidence"]
            ref = (
                f"{vendor}/{evidence['document_key']}@r{evidence['revision_no']}"
                f"#c{evidence['ordinal']}"
            )
            items.append(RetrievedItem(item["chunk_id"], ref, evidence["text"]))
        found[row.question_id] = tuple(items)
    return found


def _calls(
    run: _Run, actor: ActorContext, review_id: uuid.UUID, price: ModelPrice | None
) -> tuple[ObservedCall, ...]:
    with run.factory() as session:
        rows = session.execute(
            select(CallRow)
            .where(CallRow.tenant_id == actor.tenant_id, CallRow.review_id == review_id)
            .order_by(CallRow.question_id, CallRow.stage, CallRow.sequence)
        ).scalars()
        calls = []
        for row in rows:
            cost = None
            if price is not None and row.input_tokens is not None:
                cost = price.cost(row.input_tokens, row.output_tokens or 0)
            calls.append(
                ObservedCall(
                    stage=row.stage,
                    question_id=row.question_id,
                    sequence=row.sequence,
                    outcome=row.outcome,
                    rejection_reason=row.rejection_reason,
                    model_used=row.model_used,
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    latency_ms=row.latency_ms,
                    cost_usd=cost,
                )
            )
    return tuple(calls)


def _hidden(load: Callable[[], object]) -> bool:
    try:
        load()
    except ReviewNotFoundError:
        return True
    except Exception:
        return False
    return False


@dataclass(frozen=True)
class _Pair:
    tenant: str
    vendor: str

    @property
    def label(self) -> str:
        return f"{self.tenant}.{self.vendor}"


def _ground_truth(suite: Suite, pair: _Pair) -> dict[str, Any]:
    return {
        q.id: q.case_for(FINAL)
        for q in suite.questions()
        if (q.tenant, q.vendor) == (pair.tenant, pair.vendor) and q.case_for(FINAL) is not None
    }


def _gold_refs(run: _Run, pair: _Pair, case: Any) -> frozenset[str]:
    refs: set[str] = set()
    if case is None:
        return frozenset()
    for anchor_ref in case.gold:
        quote = run.suite.anchors[anchor_ref].quote
        revision = anchor_ref.revision
        for _, ordinal, chunk_text in run.chunks(
            revision.tenant, revision.vendor, revision.document, revision.n
        ):
            if quote in chunk_text:
                refs.add(f"{pair.vendor}/{revision.document}@r{revision.n}#c{ordinal}")
    return frozenset(refs)


def _review(
    run: _Run,
    pair: _Pair,
    provider: ModelProvider,
    *,
    number: int,
    phase: str,
    configuration: ReviewConfiguration,
    traps: Mapping[str, str],
    price: ModelPrice | None = None,
) -> ObservedReview:
    actor = _actor(pair.tenant)
    request = ReviewRequest(
        vendor_id=run.state.loaded.vendors[(pair.tenant, pair.vendor)],
        idempotency_key=f"eval-{run.run_id}-{number}-{pair.label}",
        identity=HASH_IDENTITY,
        configuration=configuration,
    )
    created = create_review(run.factory, actor, request)
    run.drain(provider, created.job_id)
    review_status = load_review_status(run.factory, actor, created.review_id).value
    other = _actor(_other_tenant(run.suite, pair.tenant))
    evidence = _evidence(run, actor, created.review_id, pair.vendor)
    cases = _ground_truth(run.suite, pair)
    tenant_chunks = run.tenant_chunk_ids(actor.tenant_id)
    referenced: set[str] = {item.chunk_id for items in evidence.values() for item in items}
    questions: list[ObservedQuestion] = []
    output_text = ""
    with run.factory() as session:
        wrapper = session.execute(
            select(ReviewOutputRow.wrapper_canonical).where(
                ReviewOutputRow.tenant_id == actor.tenant_id,
                ReviewOutputRow.review_id == created.review_id,
            )
        ).scalar_one_or_none()
    if wrapper is not None:
        output_text = wrapper
        stored = load_review_output(run.factory, actor, created.review_id)
        content = stored.output.content
        findings = content.content.findings
        for item in content.questions:
            question_id = item.question_id
            stage = item.verification
            value = stage.value
            claims: list[ObservedClaim] = []
            free_text: list[tuple[str, str]] = []
            status = None
            if value is not None:
                status = value.evidence_status.value
                free_text.append(("rationale", value.rationale))
                for claim in value.claims:
                    cited = tuple(
                        ObservedCitation(str(value.citations[i].chunk_id), value.citations[i].quote)
                        for i in claim.citation_indexes
                    )
                    claims.append(ObservedClaim(claim.text, cited))
                    free_text.append(("claim", claim.text))
            own = [f for f in findings if question_id in f.question_ids]
            finding_citations = tuple(
                ObservedCitation(str(c.chunk_id), c.quote) for f in own for c in f.citations
            )
            for finding in own:
                free_text += [("finding title", finding.title), ("finding", finding.statement)]
            for ref in item.findings:
                free_text += [("follow-up", text) for text in ref.follow_up_questions]
            referenced.update(c.chunk_id for claim in claims for c in claim.citations)
            referenced.update(c.chunk_id for c in finding_citations)
            case = cases.get(question_id)
            questions.append(
                ObservedQuestion(
                    question_id=question_id,
                    expected_status=None if case is None else case.expected_status.value,
                    status=status,
                    verification=stage.outcome.value,
                    unresolved_reason=None
                    if stage.unresolved_reason is None
                    else stage.unresolved_reason.value,
                    trap=traps.get(question_id),
                    retrieved=evidence.get(question_id, ()),
                    claims=tuple(claims),
                    finding_citations=finding_citations,
                    finding_count=len(item.findings),
                    free_text=tuple(free_text),
                    gold_refs=_gold_refs(run, pair, case),
                    forbidden_anchors=frozenset()
                    if case is None
                    else frozenset(str(ref) for ref in case.forbidden),
                )
            )
    return ObservedReview(
        run=number,
        phase=phase,
        tenant=pair.tenant,
        vendor=pair.vendor,
        configuration_sha256=configuration.configuration_sha256,
        review_status=review_status,
        questions=tuple(questions),
        calls=_calls(run, actor, created.review_id, price),
        foreign_review_hidden=_hidden(lambda: load_review(run.factory, other, created.review_id)),
        foreign_output_hidden=_hidden(
            lambda: load_review_output(run.factory, other, created.review_id)
        ),
        foreign_chunks=len(referenced - tenant_chunks),
        output_text=output_text,
        tenant_canaries=_tenant_canaries(run.suite, pair.tenant),
    )


# --- suites ---------------------------------------------------------------------------------------


def _pairs(suite: Suite) -> list[_Pair]:
    return [_Pair(tenant, vendor) for tenant, vendor in vendors_with_questions(suite)]


def _question_ids() -> tuple[str, ...]:
    return tuple(q.question_id for q in load_template(*TEMPLATE).questions)


def _foreign_item(run: _Run) -> RetrievedItem:
    tenant, vendor, document, n = FOREIGN_TRAP_SOURCE
    chunk_id, ordinal, chunk_text = run.chunks(tenant, vendor, document, n)[0]
    return RetrievedItem(str(chunk_id), f"{vendor}/{document}@r{n}#c{ordinal}", chunk_text)


def _plans(run: _Run, pair: _Pair, traps: Mapping[str, str]) -> list[contract.QuestionPlan]:
    cases = _ground_truth(run.suite, pair)
    plans = []
    for question_id in _question_ids():
        case = cases.get(question_id)
        if case is None:
            plans.append(contract.QuestionPlan(question_id, None, trap=traps.get(question_id)))
            continue
        gold = tuple(
            contract.GoldPassage(str(ref), run.suite.anchors[ref].quote) for ref in case.gold
        )
        claim = case.acceptable_claims[0].text if case.acceptable_claims else None
        plans.append(
            contract.QuestionPlan(
                question_id,
                case.expected_status.value,
                gold,
                claim,
                traps.get(question_id),
            )
        )
    return plans


def contract_reviews(
    run: _Run, reviews: list[ObservedReview], *, rationale_extra: str | None = None
) -> None:
    """Both contract phases for every pair, appended to ``reviews`` as they finish (a deadline
    stop keeps the reviews already done for the partial record)."""
    configuration = review_configuration(contract.CONTRACT_MODEL_ID)
    foreign = _foreign_item(run)
    for pair in _pairs(run.suite):
        traps = CONTRACT_TRAPS.get((pair.tenant, pair.vendor), {})
        refusal = _review(
            run,
            pair,
            contract.refusal_provider(_question_ids()),
            number=1,
            phase="refusal",
            configuration=configuration,
            traps={},
        )
        reviews.append(refusal)
        retrieved = {q.question_id: q.retrieved for q in refusal.questions}
        phase = contract.scripted_provider(
            _plans(run, pair, traps), retrieved, foreign=foreign, rationale_extra=rationale_extra
        )
        reviews.append(
            _review(
                run,
                pair,
                phase.provider,
                number=2,
                phase="scripted",
                configuration=configuration,
                traps=traps,
            )
        )


@dataclass(frozen=True)
class LiveSetup:
    selection: Selection
    pricing: Pricing
    price: ModelPrice
    key: SecretStr
    committed_usd: Decimal


def committed_records(root: Path) -> list[dict[str, Any]]:
    directory = root / cli.RUNS_DIRECTORY
    if not directory.is_dir():
        return []
    return [parse_record(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def live_preflight(
    options: cli.RunOptions,
    *,
    root: Path,
    git: GitRunner,
    today: date,
) -> LiveSetup:
    """Every live refusal, in order, before any database or provider exists (module
    docstring). Returns what the run needs; raises ``EvaluationRefusal`` (exit 3 or 4)."""
    assert options.model is not None and options.budget_usd is not None
    selection_path = root / "docs" / "evaluation" / "selection.toml"
    pricing_path = root / "docs" / "evaluation" / "pricing.toml"
    try:
        selection_bytes = selection_path.read_bytes()
    except OSError:
        raise refuse("docs/evaluation/selection.toml cannot be read") from None
    selection = parse_selection(selection_bytes)
    committed = committed_cost(committed_records(root))
    budget_rules.require_open_cap(
        total_cap=selection.total_usd_cap,
        committed_usd=committed,
        budget_usd=options.budget_usd,
    )
    require_live_selection(selection, options.model)
    try:
        pricing = parse_pricing(pricing_path.read_bytes())
    except OSError:
        raise refuse("docs/evaluation/pricing.toml cannot be read") from None
    price = pricing.price(options.model)
    if pricing.is_stale(today):
        print(f"{cli.PROG}: warning: pricing.toml as_of is over 30 days old", file=sys.stderr)
    key = _api_key()
    require_clean_tree(git)
    reviews = options.runs * len(_live_pairs(root, options.variant))
    configuration = review_configuration(options.model)
    ceiling = budget_rules.preflight_ceiling(
        reviews=reviews, price=price, max_output_tokens=configuration.max_output_tokens
    )
    budget_rules.check_preflight(
        ceiling=ceiling,
        budget_usd=options.budget_usd,
        total_cap=selection.total_usd_cap,
        committed_usd=committed,
    )
    return LiveSetup(selection, pricing, price, key, committed)


def _api_key() -> SecretStr:
    """``EG_ANTHROPIC_API_KEY`` through the W8 loader (exit 3 naming the variable only)."""
    message: str | None = None
    key: SecretStr | None = None
    try:
        key = load_anthropic_settings().anthropic_api_key
    except ReviewConfigurationError as error:
        message = str(error)  # names the variable, never the value
    if key is None:
        raise refuse(message or "EG_ANTHROPIC_API_KEY is not valid")
    return key


def _live_pairs(root: Path, variant: str) -> list[_Pair]:
    return _pairs(load_suite(root / "sample_data", variant))


def _https_transport(key: SecretStr) -> AnthropicTransport:
    return HttpsAnthropicTransport(key)


def live_reviews(
    run: _Run, setup: LiveSetup, provider: budget_rules.BudgetGuard, options: cli.RunOptions
) -> tuple[list[ObservedReview], str | None]:
    assert options.model is not None
    configuration = review_configuration(options.model)
    reviews: list[ObservedReview] = []
    stopped: str | None = None
    try:
        for number in range(1, options.runs + 1):
            for pair in _pairs(run.suite):
                if provider.exhausted:
                    raise _Stopped("budget_stopped")
                run.check_deadline()
                reviews.append(
                    _review(
                        run,
                        pair,
                        provider,
                        number=number,
                        phase="live",
                        configuration=configuration,
                        traps={},
                        price=setup.price,
                    )
                )
        if provider.exhausted:
            stopped = "budget_stopped"
    except _Stopped as stop:
        stopped = stop.reason
    return reviews, stopped


# --- the runner -----------------------------------------------------------------------------------


@dataclass
class Environment:
    """What ``run_suite`` reads from the outside world; tests replace parts of it."""

    root: Path = ROOT
    git: GitRunner = _git
    transport_factory: TransportFactory = _https_transport
    clock: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    rationale_extra: str | None = None
    """Test hook: text appended to one scripted rationale (the canary negative control)."""
    database_url: URL | None = None
    """Test hook: an already guarded URL (the integration tests' ``_test`` database)."""


def _slug(model: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", model.lower()).strip("-")


def _context(
    options: cli.RunOptions,
    environment: Environment,
    suite: Suite,
    clean: Suite,
    injected: Suite,
    run_id: str,
    setup: LiveSetup | None,
) -> RunContext:
    template = load_template(*TEMPLATE)
    verifier, _ = load_prompt("verifier", 1)
    analyst, _ = load_prompt("risk_analyst", 1)
    return RunContext(
        run_id=run_id,
        suite=options.suite,
        variant=options.variant,
        created_at=environment.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_sha=_git_sha(environment.git),
        corpus_digest=corpus_digest(suite.variant, suite.effective_files),
        template_digest=template.ref.sha256,
        prompt_digests={"verifier": verifier.ref.sha256, "risk_analyst": analyst.ref.sha256},
        model_requested=options.model or contract.CONTRACT_MODEL_ID,
        runs=options.runs,
        anchors=_anchors(suite),
        injected_markers=injected_markers(clean, injected),
        selection_digest=None if setup is None else setup.selection.digest,
        pricing_digest=None if setup is None else setup.pricing.digest,
        pricing_as_of=None if setup is None else setup.pricing.as_of.isoformat(),
        pricing_source_url=None if setup is None else setup.pricing.source_url,
    )


def _write(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(record_bytes(record))


def _execute(options: cli.RunOptions, environment: Environment) -> int:
    root = environment.root
    setup: LiveSetup | None = None
    if options.suite == "live":
        setup = live_preflight(
            options,
            root=root,
            git=environment.git,
            today=environment.now().date(),
        )
    url = environment.database_url or eval_database_url(os.environ)
    sample = root / "sample_data"
    if not (sample / "corpus.toml").is_file():
        raise refuse("sample_data/ is missing; eg-eval runs from a source checkout")
    clean = load_suite(sample, "clean")
    injected = load_suite(sample, INJECTED)
    suite = injected if options.variant == INJECTED else clean
    deadline = environment.clock() + options.deadline_minutes * 60
    run_id = uuid.uuid4().hex
    engine, factory, state = _prepare(url, suite)
    try:
        run = _Run(factory, suite, state, run_id, deadline, environment.clock)
        context = _context(options, environment, suite, clean, injected, run_id, setup)
        stopped: str | None = None
        budget: dict[str, Any] | None = None
        reviews: list[ObservedReview] = []
        if setup is None:
            try:
                contract_reviews(run, reviews, rationale_extra=environment.rationale_extra)
            except _Stopped as stop:
                stopped = stop.reason
            assert options.output is not None
            target = options.output
        else:
            assert options.model is not None and options.budget_usd is not None
            guard = budget_rules.BudgetGuard(
                AnthropicProvider(environment.transport_factory(setup.key)),
                price=setup.price,
                budget_usd=options.budget_usd,
            )
            reviews, stopped = live_reviews(run, setup, guard, options)
            budget = {
                "budget_usd": format(options.budget_usd, "f"),
                "spent_usd": format(guard.totals.spent_usd.quantize(Decimal("0.000001")), "f"),
                "dispatched_calls": guard.totals.dispatched_calls,
                "refused_calls": guard.totals.refused_calls,
                "stopped": guard.stopped or stopped == "budget_stopped",
            }
            stamp = environment.now().strftime("%Y%m%dT%H%M%SZ")
            name = f"{stamp}-{_slug(options.model)}-{options.variant}-r{options.runs}.json"
            target = root / cli.RUNS_DIRECTORY / name
        record = build_record(context, reviews, stopped=stopped, budget=budget)
        _write(target, record)
    finally:
        engine.dispose()
    print(f"record: {target}")
    print(f"status: {record['status']}")
    print(f"deterministic_sha256: {record['deterministic_sha256']}")
    return exit_code_for(record["status"])


def exit_code_for(status: str) -> int:
    """The exit code of a written record: 6 stopped, 5 hard failure, 0 completed."""
    if status in ("budget_stopped", "deadline_stopped"):
        return EXIT_STOPPED
    if status == "hard_failure":
        return EXIT_HARD_FAILURE
    if status == "completed":
        return EXIT_OK
    raise ValueError("unknown record status")


def run_suite(options: cli.RunOptions, environment: Environment | None = None) -> int:
    """Run one suite and return the exit code (module docstring). Messages name variables and
    files, never values; any other failure is a fixed generic message (exit 1)."""
    try:
        return _execute(options, environment or Environment())
    except EvaluationRefusal as refusal:
        message, code = refusal.message, refusal.exit_code
    except AnthropicError:
        message, code = "the provider transport could not be configured", EXIT_CONFIGURATION
    except Exception:
        message, code = "the evaluation run failed", EXIT_RUNTIME
    print(f"{cli.PROG}: error: {message}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """The installed ``eg-eval`` command."""
    return cli.main(argv, runner=run_suite, root=ROOT)


if __name__ == "__main__":
    sys.exit(main())
