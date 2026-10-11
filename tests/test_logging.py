import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evidenceguard_api import __main__ as cli
from evidenceguard_api.app import create_app
from evidenceguard_observability.jsonlog import (
    REQUEST_COMPLETED,
    UNREVIEWED_EVENT,
    JsonFormatter,
    configure_logging,
    log_event,
    logging_config,
)

# Obviously fake marker standing in for sensitive submitted input; not a credential.
SUBMITTED_MARKER = "submitted-marker-value"
EXCEPTION_TEXT = "internal failure detail that must stay private"


def _app() -> FastAPI:
    app = create_app()

    @app.get("/test-only/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/test-only/boom")
    def boom() -> None:
        raise RuntimeError(EXCEPTION_TEXT)

    return app


def _completion_logs(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    formatter = JsonFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if record.name == "evidenceguard.request"
    ]


@pytest.fixture
def capture(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="evidenceguard")
    return caplog


def test_completion_log_is_structured(capture: pytest.LogCaptureFixture) -> None:
    supplied = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

    TestClient(_app()).get("/test-only/items/42", headers={"X-Request-ID": supplied})

    (entry,) = _completion_logs(capture)
    assert entry["event"] == "request.completed"
    assert entry["level"] == "INFO"
    assert entry["request_id"] == supplied
    assert entry["method"] == "GET"
    assert entry["route"] == "/test-only/items/{item_id}"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], float) and entry["duration_ms"] >= 0


def test_unmatched_path_and_query_are_not_logged(capture: pytest.LogCaptureFixture) -> None:
    TestClient(_app()).get(f"/no-such-route/{SUBMITTED_MARKER}", params={"token": SUBMITTED_MARKER})

    (entry,) = _completion_logs(capture)
    assert entry["status"] == 404
    assert entry["route"] is None
    assert SUBMITTED_MARKER not in json.dumps(entry)
    assert SUBMITTED_MARKER not in capture.text


def test_validation_input_is_not_logged(capture: pytest.LogCaptureFixture) -> None:
    TestClient(_app()).get(f"/test-only/items/{SUBMITTED_MARKER}")

    (entry,) = _completion_logs(capture)
    assert entry["status"] == 422
    assert entry["route"] == "/test-only/items/{item_id}"
    assert SUBMITTED_MARKER not in capture.text


def test_unexpected_error_logs_type_but_not_message(capture: pytest.LogCaptureFixture) -> None:
    TestClient(_app(), raise_server_exceptions=False).get("/test-only/boom")

    (entry,) = _completion_logs(capture)
    assert entry["level"] == "ERROR"
    assert entry["status"] == 500
    assert entry["error_type"] == "RuntimeError"
    assert EXCEPTION_TEXT not in json.dumps(entry)
    assert EXCEPTION_TEXT not in capture.text
    assert all(record.exc_info is None for record in capture.records)


def _format(
    name: str,
    msg: object,
    args: tuple[object, ...] = (),
    *,
    exc_info: Any = None,
    fields: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    logger = logging.getLogger(name)
    extra = {"evidenceguard_fields": fields} if fields is not None else None
    record = logger.makeRecord(
        name, logging.ERROR, __file__, 1, msg, args, exc_info=exc_info, extra=extra
    )
    text = JsonFormatter().format(record)
    entry: dict[str, Any] = json.loads(text)
    return text, entry


def test_formatter_drops_unlisted_fields_and_exception_details() -> None:
    text, entry = _format(
        "evidenceguard.test",
        "something.failed",
        exc_info=(RuntimeError, RuntimeError(EXCEPTION_TEXT), None),
        fields={"status": 500, "quote": SUBMITTED_MARKER},
    )

    assert entry["event"] == UNREVIEWED_EVENT
    assert entry["status"] == 500
    assert "quote" not in entry
    assert SUBMITTED_MARKER not in text
    assert EXCEPTION_TEXT not in text


@pytest.mark.parametrize("logger_name", ["evidenceguard.request", "uvicorn.error"])
def test_marker_embedded_in_a_message_is_not_written(logger_name: str) -> None:
    text, entry = _format(logger_name, f"lookup failed for {SUBMITTED_MARKER}")

    assert entry["event"] == UNREVIEWED_EVENT
    assert SUBMITTED_MARKER not in text


@pytest.mark.parametrize("logger_name", ["evidenceguard.request", "uvicorn.error"])
def test_marker_in_interpolation_arguments_is_not_written(logger_name: str) -> None:
    text, entry = _format(logger_name, "lookup failed for %s", (SUBMITTED_MARKER,))

    assert entry["event"] == UNREVIEWED_EVENT
    assert SUBMITTED_MARKER not in text


@pytest.mark.parametrize("logger_name", ["evidenceguard.request", "uvicorn.error"])
def test_exception_interpolated_into_a_message_is_not_written(logger_name: str) -> None:
    text, entry = _format(logger_name, "failed: %s", (RuntimeError(EXCEPTION_TEXT),))

    assert entry["event"] == UNREVIEWED_EVENT
    assert EXCEPTION_TEXT not in text
    assert "RuntimeError" not in text


def test_reviewed_template_drops_its_arguments() -> None:
    text, entry = _format("uvicorn.error", "Started server process [%d]", (424242,))

    assert entry["event"] == "server.process_started"
    assert "424242" not in text


def test_uvicorn_unhandled_exception_record_has_no_exception_text() -> None:
    text, entry = _format(
        "uvicorn.error",
        "Exception in ASGI application\n",
        exc_info=(RuntimeError, RuntimeError(EXCEPTION_TEXT), None),
    )

    assert entry["event"] == "server.unhandled_exception"
    assert EXCEPTION_TEXT not in text
    assert "Traceback" not in text


def test_request_completed_event_keeps_its_safe_fields() -> None:
    fields = {
        "request_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "method": "GET",
        "route": "/healthz",
        "status": 200,
        "duration_ms": 1.5,
    }

    _, entry = _format("evidenceguard.request", REQUEST_COMPLETED, fields=fields)

    assert entry["event"] == REQUEST_COMPLETED
    assert {key: entry[key] for key in fields} == fields


def test_several_app_instances_do_not_duplicate_logs(capture: pytest.LogCaptureFixture) -> None:
    apps = [_app() for _ in range(3)]

    TestClient(apps[1]).get("/healthz")

    assert len(_completion_logs(capture)) == 1
    assert logging.getLogger("evidenceguard.request").handlers == []


_LOGGER_NAMES = ("evidenceguard", "uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture
def restore_loggers() -> Iterator[None]:
    saved = {
        name: (list(lg.handlers), lg.level, lg.propagate)
        for name, lg in ((n, logging.getLogger(n)) for n in _LOGGER_NAMES)
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.mark.usefixtures("restore_loggers")
def test_configure_logging_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    configure_logging()

    logger = logging.getLogger("evidenceguard")
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JsonFormatter)
    assert logging.getLogger("uvicorn.access").handlers == []

    log_event(logging.getLogger("evidenceguard.request"), "request.completed", status=200)
    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == 200


def test_eg_api_uses_json_logging_and_disables_the_access_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))

    cli.main(["--port", "8765"])

    (kwargs,) = calls
    assert kwargs["access_log"] is False
    assert kwargs["log_config"] == logging_config()
    assert kwargs["port"] == 8765
