"""Functional tests for the /internal/metrics Prometheus endpoint.

Uses a minimal self-contained FastAPI app that mounts the real metrics
router + TenantTaggingMiddleware. This avoids pulling in
``voyagent_api.main`` (and its auth / DB startup surface) for a test
that only cares about the metrics wiring.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voyagent_api.metrics import router as metrics_router  # noqa: E402
from voyagent_api.observability import TenantTaggingMiddleware  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    app.add_middleware(TenantTaggingMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.fixture
def local_client() -> TestClient:
    """TestClient that appears to come from 127.0.0.1."""
    app = _build_app()
    # httpx-based Starlette TestClient exposes a ``client`` kwarg for the
    # (host, port) tuple surfaced as ``request.client``.
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def public_client() -> TestClient:
    """TestClient that appears to come from a public IP."""
    app = _build_app()
    return TestClient(app, client=("203.0.113.42", 50001))


# --------------------------------------------------------------------------- #
# Access control                                                              #
# --------------------------------------------------------------------------- #


def test_metrics_endpoint_accessible_from_localhost(local_client: TestClient) -> None:
    r = local_client.get("/internal/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")


def test_metrics_endpoint_rejects_public_with_no_token(
    public_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOYAGENT_METRICS_TOKEN", "secret123")
    r = public_client.get("/internal/metrics")
    # 404 on purpose — the endpoint refuses to advertise itself publicly.
    assert r.status_code == 404


def test_metrics_endpoint_accepts_token_from_any_host(
    public_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOYAGENT_METRICS_TOKEN", "secret123")
    r = public_client.get(
        "/internal/metrics",
        headers={"X-Voyagent-Metrics-Token": "secret123"},
    )
    assert r.status_code == 200


def test_metrics_endpoint_rejects_wrong_token(
    public_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOYAGENT_METRICS_TOKEN", "secret123")
    r = public_client.get(
        "/internal/metrics",
        headers={"X-Voyagent-Metrics-Token": "wrong"},
    )
    assert r.status_code == 404


def test_metrics_endpoint_disabled_when_token_unset_and_not_localhost(
    public_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VOYAGENT_METRICS_TOKEN", raising=False)
    r = public_client.get(
        "/internal/metrics",
        headers={"X-Voyagent-Metrics-Token": "anything"},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Exposition-format content                                                   #
# --------------------------------------------------------------------------- #


def test_metrics_output_has_build_info(local_client: TestClient) -> None:
    r = local_client.get("/internal/metrics")
    assert r.status_code == 200
    assert re.search(
        r'voyagent_api_build_info\{[^}]*version="[^"]+"[^}]*\}\s+1',
        r.text,
    ), f"build_info line missing; body was:\n{r.text}"


def test_metrics_output_has_requests_total_counter(local_client: TestClient) -> None:
    # Drive traffic through the middleware so the counter actually ticks.
    for _ in range(3):
        assert local_client.get("/health").status_code == 200

    r = local_client.get("/internal/metrics")
    assert r.status_code == 200
    # Look for any non-zero counter sample.
    matches = re.findall(
        r"^voyagent_api_requests_total\{[^}]*\}\s+([0-9.e+]+)",
        r.text,
        re.MULTILINE,
    )
    assert matches, f"no requests_total samples found; body:\n{r.text}"
    assert any(float(v) > 0 for v in matches)


def test_metrics_output_has_request_duration_histogram(
    local_client: TestClient,
) -> None:
    local_client.get("/health")
    r = local_client.get("/internal/metrics")
    assert r.status_code == 200
    # Either a real prometheus_client histogram (with _bucket{le="..."})
    # or the hand-rolled fallback (which exposes _sum / _count as a
    # summary). Accept either — production code supports both paths.
    has_bucket = bool(
        re.search(
            r'voyagent_api_request_duration_seconds_bucket\{[^}]*le="[^"]+"[^}]*\}\s+[0-9.e+]+',
            r.text,
        )
    )
    has_summary = bool(
        re.search(r"voyagent_api_request_duration_seconds_count\{", r.text)
    )
    assert has_bucket or has_summary, (
        f"duration histogram/summary missing; body:\n{r.text}"
    )


def test_metrics_output_has_active_sessions_gauge(local_client: TestClient) -> None:
    r = local_client.get("/internal/metrics")
    assert r.status_code == 200
    m = re.search(
        r"^voyagent_api_active_sessions(?:\{[^}]*\})?\s+([0-9.e+-]+)",
        r.text,
        re.MULTILINE,
    )
    assert m, f"active_sessions gauge missing; body:\n{r.text}"
    # Must be numeric (stub currently returns 0, but don't hard-code that).
    float(m.group(1))
