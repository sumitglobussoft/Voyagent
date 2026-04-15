"""Prometheus metrics endpoint for voyagent-api.

Exposes ``GET /internal/metrics`` in Prometheus text exposition format.

Access is gated: the endpoint only answers requests that originate from
``127.0.0.1`` / ``::1`` **or** that carry the shared secret in the
``X-Voyagent-Metrics-Token`` header (matching ``VOYAGENT_METRICS_TOKEN``).
This keeps the endpoint reachable for local scrapers and in-cluster
Prometheus while refusing drive-by public access.

If ``prometheus-client`` is installed we use it; otherwise we fall back
to a tiny hand-rolled registry so the module is importable without the
extra dependency. The hand-rolled path is good enough for an MVP scrape.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

# --------------------------------------------------------------------------- #
# Registry (prometheus-client if available, else hand-rolled)                 #
# --------------------------------------------------------------------------- #

try:
    from prometheus_client import (  # type: ignore[import-not-found]
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    from prometheus_client.exposition import CONTENT_TYPE_LATEST  # type: ignore[import-not-found]

    _HAS_PROM = True
    _REGISTRY = CollectorRegistry()

    _requests_total = Counter(
        "voyagent_api_requests_total",
        "Count of HTTP requests handled by the API.",
        labelnames=("method", "path", "status"),
        registry=_REGISTRY,
    )
    _request_duration = Histogram(
        "voyagent_api_request_duration_seconds",
        "HTTP request duration in seconds.",
        labelnames=("method", "path"),
        registry=_REGISTRY,
    )
    _active_sessions = Gauge(
        "voyagent_api_active_sessions",
        "Chat sessions with messages in the last hour.",
        registry=_REGISTRY,
    )
    _build_info = Gauge(
        "voyagent_api_build_info",
        "Build information for the running API.",
        labelnames=("version", "commit"),
        registry=_REGISTRY,
    )
    _build_info.labels(
        version=os.environ.get("VOYAGENT_VERSION", "0.0.0-dev"),
        commit=os.environ.get("VOYAGENT_GIT_SHA", "unknown"),
    ).set(1)
except Exception:  # noqa: BLE001
    _HAS_PROM = False
    _REGISTRY = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    _lock = threading.Lock()
    _counters: dict[tuple[str, str, str], int] = {}
    _hist_sum: dict[tuple[str, str], float] = {}
    _hist_count: dict[tuple[str, str], int] = {}


def record_request(*, method: str, path: str, status: int, duration_seconds: float) -> None:
    """Record a request for the counter + histogram.

    Called from ``TenantTaggingMiddleware``. Path is used verbatim — if
    cardinality becomes an issue we'll bucket it through the route tree
    later.
    """
    # Collapse UUID-ish / numeric path segments to keep cardinality bounded.
    bucketed = _bucket_path(path)
    if _HAS_PROM:
        _requests_total.labels(method=method, path=bucketed, status=str(status)).inc()
        _request_duration.labels(method=method, path=bucketed).observe(duration_seconds)
        return
    with _lock:
        key = (method, bucketed, str(status))
        _counters[key] = _counters.get(key, 0) + 1
        hkey = (method, bucketed)
        _hist_sum[hkey] = _hist_sum.get(hkey, 0.0) + duration_seconds
        _hist_count[hkey] = _hist_count.get(hkey, 0) + 1


def _bucket_path(path: str) -> str:
    parts = []
    for seg in path.split("/"):
        if not seg:
            parts.append(seg)
            continue
        if seg.isdigit() or (len(seg) >= 16 and "-" in seg):
            parts.append(":id")
        else:
            parts.append(seg)
    return "/".join(parts)


def _active_sessions_value() -> int:
    """Return the current active-sessions gauge value.

    STUB: wiring the real query requires reaching into the agent runtime
    / session store which is owned by a parallel agent. Returning 0 here
    keeps the metric present (so dashboards don't break) without
    speculatively importing private modules.
    """
    return 0


def _render_hand_rolled() -> str:
    lines: list[str] = []
    lines.append("# HELP voyagent_api_requests_total Count of HTTP requests handled by the API.")
    lines.append("# TYPE voyagent_api_requests_total counter")
    with _lock:
        for (method, path, status), count in sorted(_counters.items()):
            lines.append(
                f'voyagent_api_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )
        lines.append(
            "# HELP voyagent_api_request_duration_seconds HTTP request duration in seconds."
        )
        lines.append("# TYPE voyagent_api_request_duration_seconds summary")
        for (method, path), total in sorted(_hist_sum.items()):
            count = _hist_count.get((method, path), 0)
            lines.append(
                f'voyagent_api_request_duration_seconds_sum{{method="{method}",path="{path}"}} {total}'
            )
            lines.append(
                f'voyagent_api_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}'
            )
    lines.append("# HELP voyagent_api_active_sessions Chat sessions with messages in the last hour.")
    lines.append("# TYPE voyagent_api_active_sessions gauge")
    lines.append(f"voyagent_api_active_sessions {_active_sessions_value()}")
    lines.append("# HELP voyagent_api_build_info Build information for the running API.")
    lines.append("# TYPE voyagent_api_build_info gauge")
    version = os.environ.get("VOYAGENT_VERSION", "0.0.0-dev")
    commit = os.environ.get("VOYAGENT_GIT_SHA", "unknown")
    lines.append(f'voyagent_api_build_info{{version="{version}",commit="{commit}"}} 1')
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Router                                                                       #
# --------------------------------------------------------------------------- #

router = APIRouter()


def _client_is_local(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    host = client.host
    return host in {"127.0.0.1", "::1", "localhost"}


def _token_ok(request: Request) -> bool:
    expected = os.environ.get("VOYAGENT_METRICS_TOKEN", "").strip()
    if not expected:
        return False
    provided = request.headers.get("x-voyagent-metrics-token", "").strip()
    return bool(provided) and provided == expected


@router.get("/internal/metrics")
def metrics(request: Request) -> Any:
    if not (_client_is_local(request) or _token_ok(request)):
        raise HTTPException(status_code=404, detail="not found")
    # Refresh the active-sessions gauge on scrape so it's always fresh.
    if _HAS_PROM:
        _active_sessions.set(_active_sessions_value())
        body = generate_latest(_REGISTRY)
        return PlainTextResponse(body, media_type=CONTENT_TYPE_LATEST)
    return PlainTextResponse(_render_hand_rolled(), media_type=CONTENT_TYPE_LATEST)


__all__ = ("router", "record_request")
