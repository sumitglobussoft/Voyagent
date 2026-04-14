"""Command-line entry points.

``voyagent-browser-runner worker``
    Boot a long-running worker loop.

``voyagent-browser-runner submit --kind <k> --inputs <json>``
    Enqueue a one-off job against the configured queue for local
    debugging.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from .artifacts import build_artifact_sink
from .browser_pool import BrowserPool
from .client import BrowserRunnerClient
from .job import JobKind
from .queue import build_queue
from .settings import BrowserRunnerSettings
from .worker import run_forever

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _run_worker(settings: BrowserRunnerSettings) -> None:
    queue = build_queue(settings)
    artifacts = build_artifact_sink(
        bucket=settings.artifact_bucket,
        endpoint_url=settings.artifact_endpoint,
        region=settings.artifact_region,
    )
    pool = BrowserPool(settings)
    try:
        await run_forever(queue, pool, artifacts, settings)
    finally:
        await queue.aclose()
        await artifacts.aclose()


async def _run_submit(settings: BrowserRunnerSettings, args: argparse.Namespace) -> int:
    queue = build_queue(settings)
    try:
        client = BrowserRunnerClient(queue)
        inputs = json.loads(args.inputs) if args.inputs else {}
        result = await client.submit(
            JobKind(args.kind),
            inputs,
            tenant_id=args.tenant_id,
            tenant_credentials_ref=args.credentials_ref,
            timeout_s=args.timeout,
        )
        print(result.model_dump_json(indent=2))
        return 0 if result.status.value == "succeeded" else 1
    finally:
        await queue.aclose()


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(prog="voyagent-browser-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("worker", help="Run the worker loop")

    submit = sub.add_parser("submit", help="Enqueue one job and print its result.")
    submit.add_argument("--kind", required=True, help="JobKind value, e.g. 'vfs.read_status'.")
    submit.add_argument("--inputs", default="{}", help="JSON-encoded inputs dict.")
    submit.add_argument("--tenant-id", required=True, dest="tenant_id")
    submit.add_argument(
        "--credentials-ref",
        required=True,
        dest="credentials_ref",
        help="Opaque reference resolved worker-side.",
    )
    submit.add_argument("--timeout", type=float, default=180.0)

    args = parser.parse_args(argv)
    settings = BrowserRunnerSettings()

    if args.cmd == "worker":
        asyncio.run(_run_worker(settings))
        return 0
    if args.cmd == "submit":
        return asyncio.run(_run_submit(settings, args))
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = ["main"]
