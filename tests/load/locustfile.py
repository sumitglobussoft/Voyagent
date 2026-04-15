"""Locust load scenarios for Voyagent.

Locust is intentionally NOT a project dependency — it's a runtime tool,
not a library. Install it standalone with::

    uv tool install locust

Then run against the demo deployment::

    VOYAGENT_BASE_URL=https://voyagent.globusdemos.com \\
    VOYAGENT_DEMO_EMAIL=demo@voyagent.globusdemos.com \\
    VOYAGENT_DEMO_PASSWORD=DemoPassword123! \\
    locust -f tests/load/locustfile.py \\
           --users 20 --spawn-rate 2 --run-time 2m --headless \\
           --host $VOYAGENT_BASE_URL

Scenarios exercised (see ``scenarios.md`` for the rationale):

* ``health`` — cheapest endpoint, sanity check + baseline.
* ``list_sessions`` / ``list_enquiries`` — authed reads, exercise RLS.
* ``create_session`` — authed write, exercises the chat-session insert
  path and the audit log.

We deliberately do NOT load-test the agent runtime itself (LLM calls
cost money + add noise). The goal here is to stress the HTTP/FastAPI +
Postgres + auth layers, which are the real bottleneck in practice.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from locust import HttpUser, between, events, task


DEFAULT_EMAIL = "demo@voyagent.globusdemos.com"
DEFAULT_PASSWORD = "DemoPassword123!"  # overridden via env


def _demo_credentials() -> tuple[str, str]:
    email = os.environ.get("VOYAGENT_DEMO_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("VOYAGENT_DEMO_PASSWORD", DEFAULT_PASSWORD)
    return email, password


class AgentRuntimeUser(HttpUser):
    """Simulated signed-in user hitting the main read/write endpoints."""

    wait_time = between(1, 3)

    access_token: str | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def on_start(self) -> None:
        """Sign in once per simulated user. Fall back to sign-up if the
        demo account is missing (e.g. a fresh deployment)."""
        email, password = _demo_credentials()
        r = self.client.post(
            "/api/auth/sign-in",
            json={"email": email, "password": password},
            name="auth:sign-in",
            catch_response=True,
        )
        if r.status_code < 400 and "access_token" in (r.json() or {}):
            self.access_token = r.json()["access_token"]
            r.success()
            return
        r.failure(f"sign-in failed: {r.status_code}")

        # Fallback: mint a fresh user so the load test still runs.
        suffix = uuid.uuid4().hex[:10]
        signup = self.client.post(
            "/api/auth/sign-up",
            json={
                "email": f"load-{suffix}@mailinator.com",
                "password": "LoadTesterPass123!",
                "full_name": "Load Tester",
                "agency_name": f"Load Agency {suffix}",
            },
            name="auth:sign-up",
        )
        if signup.status_code < 400:
            self.access_token = (signup.json() or {}).get("access_token")

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _auth_headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    # ------------------------------------------------------------------ #
    # Tasks                                                              #
    # ------------------------------------------------------------------ #

    @task(5)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(3)
    def list_sessions(self) -> None:
        self.client.get(
            "/api/chat/sessions",
            headers=self._auth_headers(),
            name="GET /api/chat/sessions",
        )

    @task(2)
    def list_enquiries(self) -> None:
        self.client.get(
            "/api/enquiries",
            headers=self._auth_headers(),
            name="GET /api/enquiries",
        )

    @task(1)
    def create_session(self) -> None:
        self.client.post(
            "/api/chat/sessions",
            json={},
            headers=self._auth_headers(),
            name="POST /api/chat/sessions",
        )


@events.quitting.add_listener
def _assert_sla(environment: Any, **_: Any) -> None:
    """Fail the run if the 95th percentile budget is blown.

    Gives the CI job a meaningful exit code when the load baseline
    regresses — otherwise locust always exits 0 and silent regressions
    slip through.
    """
    stats = environment.stats.total
    # 500 ms p95 is the documented 20-user baseline in scenarios.md.
    if stats.num_requests == 0:
        return
    p95 = stats.get_response_time_percentile(0.95)
    if p95 > 500:
        environment.process_exit_code = 1
