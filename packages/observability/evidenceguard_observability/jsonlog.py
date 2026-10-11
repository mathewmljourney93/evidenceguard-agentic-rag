"""Structured JSON logging built on the standard library.

What ``JsonFormatter`` writes for each record:

- ``timestamp``, ``level`` and ``logger`` (the logger's name, which is defined in code).
- ``event``: a **reviewed, fixed identifier**, looked up from ``REVIEWED_EVENTS`` by the
  record's *unformatted* message template. The formatter never calls ``getMessage()`` and
  never reads the record's arguments. A message not in the table becomes ``UNREVIEWED_EVENT``,
  so nothing from its text, arguments or any interpolated exception is copied.
- Only allowlisted structured fields (see ``ALLOWED_FIELDS``). Any other field attached to a
  record is dropped.
- Never exception details (``exc_info``) or stack traces. Records may carry ``error_type``,
  the exception class name only.

These guarantees cover records rendered by this formatter, which ``logging_config`` attaches to
the EvidenceGuard and Uvicorn loggers. Handlers configured elsewhere (for example a root
logger set up by another tool) are outside this control.

``create_app()`` attaches no handlers. Handlers come only from ``configure_logging`` or from
Uvicorn applying ``logging_config``, so creating several apps cannot duplicate log lines.
"""

import json
import logging
import logging.config
from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

LOGGER_NAMESPACE = "evidenceguard"
FIELDS_ATTRIBUTE = "evidenceguard_fields"
ALLOWED_FIELDS = frozenset({"request_id", "method", "route", "status", "duration_ms", "error_type"})

REQUEST_COMPLETED = "request.completed"
UNREVIEWED_EVENT = "log.unreviewed_message"

# Message template -> fixed event identifier. Templates are matched exactly; their arguments
# (process IDs, addresses, exception objects, ...) are never written.
REVIEWED_EVENTS: Mapping[str, str] = MappingProxyType(
    {
        REQUEST_COMPLETED: REQUEST_COMPLETED,
        # Uvicorn 0.54 (uvicorn/server.py, config.py, lifespan/on.py, protocols/http/*).
        "Started server process [%d]": "server.process_started",
        "Finished server process [%d]": "server.process_finished",
        "Waiting for application startup.": "server.startup_waiting",
        "Application startup complete.": "server.startup_complete",
        "Application startup failed. Exiting.": "server.startup_failed",
        "Waiting for application shutdown.": "server.shutdown_waiting",
        "Application shutdown complete.": "server.shutdown_complete",
        "Application shutdown failed. Exiting.": "server.shutdown_failed",
        "Shutting down": "server.shutting_down",
        "Uvicorn running on %s://%s:%d (Press CTRL+C to quit)": "server.listening",
        "Uvicorn running on %s://[%s]:%d (Press CTRL+C to quit)": "server.listening",
        "Exception in ASGI application\n": "server.unhandled_exception",
    }
)


def event_identifier(record: logging.LogRecord) -> str:
    """The reviewed identifier for ``record``'s message template, or ``UNREVIEWED_EVENT``."""
    template = record.msg
    if isinstance(template, str):
        return REVIEWED_EVENTS.get(template, UNREVIEWED_EVENT)
    return UNREVIEWED_EVENT


class JsonFormatter(logging.Formatter):
    """Render a record as one JSON object per line (see the module docstring for the rules)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event_identifier(record),
        }
        fields = getattr(record, FIELDS_ATTRIBUTE, None)
        if isinstance(fields, Mapping):
            for key in sorted(ALLOWED_FIELDS & fields.keys()):
                payload[key] = fields[key]
        return json.dumps(payload, separators=(",", ":"), default=str)


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Log a fixed event name with structured fields.

    ``event`` should be a key of ``REVIEWED_EVENTS``; anything else is written as
    ``UNREVIEWED_EVENT``. Fields outside ``ALLOWED_FIELDS`` are dropped.
    """
    logger.log(level, event, extra={FIELDS_ATTRIBUTE: fields})


def logging_config(level: str = "INFO") -> dict[str, Any]:
    """A ``logging.config.dictConfig`` mapping for EvidenceGuard and Uvicorn loggers.

    It replaces (rather than adds) handlers, so applying it twice still leaves one handler per
    logger. Uvicorn's access logger is silenced because it writes raw paths and query strings;
    EvidenceGuard's own request log replaces it.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": f"{__name__}.JsonFormatter"}},
        "handlers": {
            "json": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stderr",
            }
        },
        "loggers": {
            LOGGER_NAMESPACE: {"handlers": ["json"], "level": level, "propagate": False},
            "uvicorn": {"handlers": ["json"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["json"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
        },
    }


def configure_logging(level: str = "INFO") -> None:
    """Apply ``logging_config``. Safe to call more than once."""
    logging.config.dictConfig(logging_config(level))
