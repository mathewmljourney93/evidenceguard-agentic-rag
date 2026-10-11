"""``eg-api`` console entry point: serve the API with Uvicorn."""

import argparse
from collections.abc import Sequence

import uvicorn

from evidenceguard_api.app import create_app
from evidenceguard_observability.jsonlog import logging_config


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="eg-api", description="Run the EvidenceGuard API with Uvicorn."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="interface to bind (default: %(default)s)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="port to bind (default: %(default)s)"
    )
    args = parser.parse_args(argv)
    # Uvicorn applies the JSON logging configuration. Its access log is off because it records
    # raw paths and query strings; RequestContextMiddleware logs each request instead.
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_config=logging_config(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
