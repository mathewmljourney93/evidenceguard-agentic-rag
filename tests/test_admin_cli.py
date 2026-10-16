"""``eg-admin`` without a database: a fake store stands in for ``DatabaseAdminStore``."""

import argparse
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import entry_points
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from evidenceguard_api import admin
from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.accounts import (
    DemoUser,
    RevokeOutcome,
    UserNotInTenantError,
    demo_tenant_id,
    demo_user_id,
)
from evidenceguard_persistence.credentials import (
    NewApiKey,
    generate_api_key,
    parse_api_key,
    secret_sha256,
)
from evidenceguard_persistence.indexing import BackfillItem, BackfillOutcome, BackfillPage
from evidenceguard_persistence.models import UserRole
from evidenceguard_persistence.settings import DATABASE_URL_ENV
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

FAILURE_MARKER = "fake-internal-failure-marker"
TENANT, USER = uuid4(), uuid4()
PREFIX = "0123456789abcdef"
SECRET_MARKER = "fake-secret-marker-not-a-real-key"


class FakeStore:
    def __init__(self) -> None:
        self.created: list[tuple[UUID, UUID, NewApiKey]] = []
        self.revoked: list[tuple[UUID, str]] = []
        self.error: Exception | None = None
        self.revoke_outcome = RevokeOutcome.REVOKED
        self.events: list[str] = []
        self.seed_result: tuple[DemoUser, ...] | None = None
        self.backfills: list[tuple[UUID, int, UUID | None]] = []
        self.backfill_page = BackfillPage(items=(), next_after=None)

    def _maybe_fail(self) -> None:
        if self.error is not None:
            raise self.error

    def seed_demo(self) -> tuple[DemoUser, ...]:
        self._maybe_fail()
        if self.seed_result is not None:
            return self.seed_result
        return tuple(
            DemoUser("demo-tenant", TENANT, uuid4(), role, created=index == 0)
            for index, role in enumerate(UserRole)
        )

    def create_api_key(self, tenant_id: UUID, user_id: UUID, key: NewApiKey) -> UUID:
        self.events.append("create-started")
        self._maybe_fail()
        self.created.append((tenant_id, user_id, key))
        self.events.append("committed")
        return uuid4()

    def revoke_api_key(self, tenant_id: UUID, prefix: str) -> RevokeOutcome:
        self._maybe_fail()
        self.revoked.append((tenant_id, prefix))
        return self.revoke_outcome

    def backfill_indexes(self, tenant_id: UUID, *, limit: int, after: UUID | None) -> BackfillPage:
        self._maybe_fail()
        self.backfills.append((tenant_id, limit, after))
        return self.backfill_page


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _run(store: FakeStore, *argv: str) -> int:
    @contextmanager
    def factory() -> Iterator[FakeStore]:
        yield store

    return admin.main(list(argv), store_factory=factory)


# --- registration and help --------------------------------------------------------------


def test_eg_admin_console_script_is_registered() -> None:
    (script,) = entry_points(group="console_scripts", name="eg-admin")

    assert script.value == "evidenceguard_api.admin:main"
    assert script.load() is admin.main


@pytest.mark.parametrize(
    "argv",
    [["--help"], ["seed-demo", "--help"], ["create-key", "--help"], ["revoke-key", "--help"]],
)
def test_help_needs_no_database_settings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    with pytest.raises(SystemExit) as exit_info:
        admin.main(argv)

    assert exit_info.value.code == 0
    assert "usage: eg-admin" in capsys.readouterr().out


def test_help_in_a_fresh_process_without_eg_variables() -> None:
    env = {key: value for key, value in os.environ.items() if not key.startswith("EG_")}
    result = subprocess.run(
        [sys.executable, "-I", "-m", "evidenceguard_api.admin", "create-key", "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--tenant-id" in result.stdout and "--user-id" in result.stdout


def test_create_key_takes_no_secret_argument(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        admin.main(["create-key", "--tenant-id", str(TENANT), "--user-id", str(USER), "--key", "x"])

    assert exit_info.value.code == 2


# --- create-key -------------------------------------------------------------------------


def test_create_key_prints_the_key_once_after_the_store_commits(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(store, "create-key", "--tenant-id", str(TENANT), "--user-id", str(USER))
    out, err = capsys.readouterr()

    assert code == 0
    assert store.events == ["create-started", "committed"]
    ((tenant_id, user_id, key),) = store.created
    assert (tenant_id, user_id) == (TENANT, USER)
    plaintext = key.plaintext.get_secret_value()
    assert out == plaintext + "\n"
    assert out.count(plaintext) == 1
    assert plaintext not in err
    parsed = parse_api_key(plaintext)
    assert parsed is not None
    assert key.secret_sha256 == secret_sha256(parsed.secret.get_secret_value())
    assert f"prefix={key.prefix}" in err


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (UserNotInTenantError(), "the user does not exist in that tenant"),
        (
            OperationalError("INSERT", {}, Exception(FAILURE_MARKER)),
            "the database operation failed",
        ),
        (RuntimeError(FAILURE_MARKER), "unexpected RuntimeError"),
    ],
)
def test_create_key_failure_prints_nothing_to_stdout(
    store: FakeStore, capsys: pytest.CaptureFixture[str], error: Exception, message: str
) -> None:
    store.error = error
    code = _run(store, "create-key", "--tenant-id", str(TENANT), "--user-id", str(USER))
    out, err = capsys.readouterr()

    assert code == 1
    assert out == ""
    assert err == f"eg-admin: error: {message}\n"
    assert FAILURE_MARKER not in err
    assert "egk_" not in err


def test_missing_database_settings_are_reported_safely(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    code = admin.main(["create-key", "--tenant-id", str(TENANT), "--user-id", str(USER)])
    out, err = capsys.readouterr()

    assert code == 1
    assert out == ""
    assert err == "eg-admin: error: EG_DATABASE_URL is not set\n"


def test_invalid_database_url_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV, f"mysql://someone:{FAILURE_MARKER}@db.invalid/x")
    code = admin.main(["seed-demo"])
    out, err = capsys.readouterr()

    assert code == 1
    assert out == ""
    assert err == "eg-admin: error: EG_DATABASE_URL is not a valid PostgreSQL URL\n"


# --- seed-demo and revoke-key -----------------------------------------------------------


def test_seed_demo_prints_ids_and_creates_no_keys(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(store, "seed-demo")
    out, _ = capsys.readouterr()

    assert code == 0
    assert store.created == []
    assert "egk_" not in out
    assert out.count("tenant=demo-tenant") == 3
    assert "role=admin" in out and "created" in out and "existing" in out


def test_demo_ids_are_deterministic() -> None:
    assert demo_tenant_id("halverson-freight") == demo_tenant_id("halverson-freight")
    assert demo_tenant_id("halverson-freight") != demo_tenant_id("marisol-clinics")
    assert demo_user_id("marisol-clinics", UserRole.ADMIN) != demo_user_id(
        "halverson-freight", UserRole.ADMIN
    )


@pytest.mark.parametrize(
    ("outcome", "code", "out"),
    [
        (RevokeOutcome.REVOKED, 0, "revoked\n"),
        (RevokeOutcome.ALREADY_REVOKED, 0, "already revoked\n"),
        (RevokeOutcome.NOT_FOUND, 1, ""),
    ],
)
def test_revoke_key_outcomes(
    store: FakeStore,
    capsys: pytest.CaptureFixture[str],
    outcome: RevokeOutcome,
    code: int,
    out: str,
) -> None:
    store.revoke_outcome = outcome
    result = _run(store, "revoke-key", "--tenant-id", str(TENANT), "--prefix", PREFIX)
    captured = capsys.readouterr()

    assert result == code
    assert captured.out == out
    assert store.revoked == [(TENANT, PREFIX)]
    if outcome is RevokeOutcome.NOT_FOUND:
        assert captured.err == "eg-admin: error: no such key in that tenant\n"


@pytest.mark.parametrize("prefix", ["", "0123456789ABCDEF", "short", "0123456789abcdef0"])
def test_revoke_key_rejects_malformed_prefixes_without_opening_the_store(
    store: FakeStore, capsys: pytest.CaptureFixture[str], prefix: str
) -> None:
    def factory() -> None:
        raise AssertionError("store opened")

    code = admin.main(
        ["revoke-key", "--tenant-id", str(TENANT), "--prefix", prefix],
        store_factory=factory,  # type: ignore[arg-type]
    )

    assert code == 1
    assert "16 lowercase hexadecimal" in capsys.readouterr().err


def test_seed_demo_reports_the_roles_the_store_returns(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    tenant = uuid4()
    reviewer_slot, admin_slot = uuid4(), uuid4()
    # The store reports a stored role that differs from the demo default for this user.
    store.seed_result = (
        DemoUser("demo-tenant", tenant, reviewer_slot, UserRole.APPROVER, created=False),
        DemoUser("demo-tenant", tenant, admin_slot, UserRole.ADMIN, created=True),
    )

    assert _run(store, "seed-demo") == 0
    assert capsys.readouterr().out.splitlines() == [
        f"tenant=demo-tenant tenant_id={tenant} role=approver user_id={reviewer_slot} existing",
        f"tenant=demo-tenant tenant_id={tenant} role=admin user_id={admin_slot} created",
    ]


# --- usage errors never echo submitted values -------------------------------------------


def _usage_error(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    opened: list[bool] = []

    def factory() -> FakeStore:
        opened.append(True)
        raise AssertionError("store opened")

    with pytest.raises(SystemExit) as exit_info:
        admin.main(argv, store_factory=factory)  # type: ignore[arg-type]
    out, err = capsys.readouterr()

    assert exit_info.value.code == 2
    assert opened == []
    assert out == ""
    assert err.startswith("usage: eg-admin")
    assert err.endswith(admin.USAGE_ERROR_MESSAGE)
    return out, err


@pytest.mark.parametrize(
    "argv",
    [
        # Invalid UUID values.
        ["create-key", "--tenant-id", SECRET_MARKER, "--user-id", str(USER)],
        ["create-key", "--tenant-id", str(TENANT), "--user-id", SECRET_MARKER],
        ["revoke-key", "--tenant-id", SECRET_MARKER, "--prefix", PREFIX],
        ["create-key", f"--tenant-id={SECRET_MARKER}", "--user-id", str(USER)],
        # Unknown options, with and without a value.
        ["create-key", "--tenant-id", str(TENANT), "--user-id", str(USER), "--key", SECRET_MARKER],
        [
            "create-key",
            "--tenant-id",
            str(TENANT),
            "--user-id",
            str(USER),
            f"--key={SECRET_MARKER}",
        ],
        ["seed-demo", f"--{SECRET_MARKER}"],
        [f"--{SECRET_MARKER}", "seed-demo"],
        # Abbreviations are not expanded.
        ["create-key", "--tenant", str(TENANT), "--user-id", str(USER), SECRET_MARKER],
        # Extra positional arguments.
        ["create-key", "--tenant-id", str(TENANT), "--user-id", str(USER), SECRET_MARKER],
        ["seed-demo", SECRET_MARKER],
        ["revoke-key", "--tenant-id", str(TENANT), "--prefix", PREFIX, SECRET_MARKER],
        # Unknown command.
        [SECRET_MARKER],
    ],
)
def test_usage_errors_never_echo_submitted_values(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    out, err = _usage_error(argv, capsys)

    assert SECRET_MARKER not in out + err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["create-key"],
        ["create-key", "--tenant-id", str(TENANT)],
        ["revoke-key", "--tenant-id", str(TENANT)],
        ["create-key", "--tenant-id"],
    ],
)
def test_missing_arguments_are_safe_usage_errors(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    _usage_error(argv, capsys)


def test_a_key_pasted_by_mistake_is_never_echoed(capsys: pytest.CaptureFixture[str]) -> None:
    pasted = generate_api_key().plaintext.get_secret_value()
    for argv in (
        ["create-key", "--tenant-id", pasted, "--user-id", str(USER)],
        ["create-key", "--tenant-id", str(TENANT), "--user-id", str(USER), pasted],
        [pasted],
    ):
        out, err = _usage_error(argv, capsys)
        assert pasted not in out + err
        assert pasted[21:] not in out + err


@pytest.mark.parametrize(
    "argv",
    [
        # Each case abbreviates exactly one option; every other required argument is valid.
        ["create-key", "--tenant", str(TENANT), "--user-id", str(USER)],
        ["create-key", "--tenant-i", str(TENANT), "--user-id", str(USER)],
        ["create-key", "--tenant-id", str(TENANT), "--user", str(USER)],
        ["create-key", "--tenant-id", str(TENANT), "--user-i", str(USER)],
        ["revoke-key", "--tenant", str(TENANT), "--prefix", PREFIX],
        ["revoke-key", "--tenant-id", str(TENANT), "--pre", PREFIX],
        ["revoke-key", "--tenant-id", str(TENANT), "--prefi", PREFIX],
    ],
)
def test_abbreviated_subcommand_options_are_refused(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    _usage_error(argv, capsys)


def test_unabbreviated_options_still_reach_the_store(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    # Control for the test above: the same arguments, spelled in full, are accepted.
    assert _run(store, "create-key", "--tenant-id", str(TENANT), "--user-id", str(USER)) == 0
    assert _run(store, "revoke-key", "--tenant-id", str(TENANT), "--prefix", PREFIX) == 0
    assert len(store.created) == 1 and store.revoked == [(TENANT, PREFIX)]
    capsys.readouterr()


def test_every_subparser_disables_abbreviations() -> None:
    parser = admin._parser()
    (subparsers,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert parser.allow_abbrev is False
    assert {name: sub.allow_abbrev for name, sub in subparsers.choices.items()} == {
        "seed-demo": False,
        "create-key": False,
        "revoke-key": False,
        "backfill-indexes": False,
    }
    assert all(isinstance(sub, admin.SafeArgumentParser) for sub in subparsers.choices.values())


# --- backfill-indexes (M4c, ADR-0015) --------------------------------------------------------


def _items(*outcomes: BackfillOutcome) -> tuple[BackfillItem, ...]:
    return tuple(
        BackfillItem(
            revision_id=uuid4(),
            index_id=None
            if outcome in (BackfillOutcome.INELIGIBLE, BackfillOutcome.CONFLICT)
            else uuid4(),
            outcome=outcome,
        )
        for outcome in outcomes
    )


def test_backfill_prints_only_counts_and_the_cursor(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    cursor = uuid4()
    store.backfill_page = BackfillPage(
        items=_items(BackfillOutcome.PENDING, BackfillOutcome.PENDING, BackfillOutcome.READY),
        next_after=cursor,
    )

    assert _run(store, "backfill-indexes", "--tenant-id", str(TENANT)) == 0

    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "pending=2 ready=1 stalled=0 ineligible=0 conflict=0",
        f"next_after={cursor}",
    ]
    assert err == ""
    for item in store.backfill_page.items:
        assert str(item.revision_id) not in out
    assert store.backfills == [(TENANT, 50, None)]  # the accepted default limit


def test_backfill_passes_the_limit_and_cursor_and_prints_no_cursor_at_the_end(
    store: FakeStore, capsys: pytest.CaptureFixture[str]
) -> None:
    after = uuid4()
    assert (
        _run(
            store,
            "backfill-indexes",
            "--tenant-id",
            str(TENANT),
            "--limit",
            "100",
            "--after",
            str(after),
        )
        == 0
    )
    assert store.backfills == [(TENANT, 100, after)]
    assert capsys.readouterr().out.splitlines()[-1] == "next_after=-"


@pytest.mark.parametrize(
    "outcome", [BackfillOutcome.STALLED, BackfillOutcome.INELIGIBLE, BackfillOutcome.CONFLICT]
)
def test_a_page_with_items_needing_attention_exits_three(
    store: FakeStore, capsys: pytest.CaptureFixture[str], outcome: BackfillOutcome
) -> None:
    store.backfill_page = BackfillPage(
        items=_items(BackfillOutcome.PENDING, outcome), next_after=None
    )
    assert _run(store, "backfill-indexes", "--tenant-id", str(TENANT)) == admin.EXIT_ATTENTION == 3
    assert f"{outcome.value}=1" in capsys.readouterr().out


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, Exception(FAILURE_MARKER)),
        RuntimeError(FAILURE_MARKER),
    ],
)
def test_a_backfill_failure_exits_one_with_a_fixed_message(
    store: FakeStore, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    store.error = error
    assert _run(store, "backfill-indexes", "--tenant-id", str(TENANT)) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert FAILURE_MARKER not in err
    assert err.startswith("eg-admin: error: ")


@pytest.mark.parametrize(
    "argv",
    [
        ["backfill-indexes"],
        ["backfill-indexes", "--tenant-id", SECRET_MARKER],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", "0"],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", "101"],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", "-1"],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", "1e2"],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", " 5"],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--limit", SECRET_MARKER],
        ["backfill-indexes", "--tenant-id", str(TENANT), "--after", SECRET_MARKER],
        ["backfill-indexes", "--tenant", str(TENANT)],
        ["backfill-indexes", "--tenant-id", str(TENANT), SECRET_MARKER],
    ],
)
def test_backfill_usage_errors_exit_two_without_echoing(
    store: FakeStore, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    with pytest.raises(SystemExit) as info:
        _run(store, *argv)
    assert info.value.code == 2
    out, err = capsys.readouterr()
    assert SECRET_MARKER not in out + err
    assert err.endswith(admin.USAGE_ERROR_MESSAGE)
    assert store.backfills == []


def test_backfill_uses_the_fixed_offline_identity_and_a_system_admin_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_backfill(factory: object, actor: object, **kwargs: object) -> BackfillPage:
        seen["actor"], seen["kwargs"] = actor, kwargs
        return BackfillPage(items=(), next_after=None)

    monkeypatch.setattr(admin, "backfill_index_revisions", fake_backfill)
    store = admin.DatabaseStore(object())  # type: ignore[arg-type]
    store.backfill_indexes(TENANT, limit=7, after=None)

    actor = seen["actor"]
    assert isinstance(actor, ActorContext)
    assert actor.tenant_id == TENANT
    assert actor.actor_id == admin.SYSTEM_ACTOR_ID
    assert actor.role is Role.ADMIN
    assert seen["kwargs"] == {"identity": HASH_IDENTITY, "limit": 7, "after": None}
