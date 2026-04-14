"""Runtime configuration for the browser-runner service.

Values are loaded from environment variables prefixed ``VOYAGENT_BROWSER_``.
All settings have conservative defaults — a developer can ``uv run
voyagent-browser-runner worker`` against ``infra/docker/dev.yml`` without
further configuration.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BrowserRunnerSettings(BaseSettings):
    """Env-driven configuration for :class:`Worker`, :class:`BrowserPool`,
    and the queue/artifact factories.

    DB 1 is used by default so the worker does not collide with the offer
    cache that the agent runtime keeps on DB 0.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_BROWSER_",
        case_sensitive=False,
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://localhost:6379/1",
        description="Redis URL for the job queue and result store. DB 1 by convention.",
    )
    queue_name: str = Field(
        default="voyagent:browser_jobs",
        description="Base key for the job list and the result-hash namespace.",
    )
    result_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="How long to retain a JobResult in Redis before eviction.",
    )
    max_concurrency: int = Field(
        default=3,
        ge=1,
        description="Maximum concurrent Playwright browser contexts per worker.",
    )
    headless: bool = Field(
        default=True,
        description="Whether Playwright runs headless. Set False for local debugging.",
    )
    browser: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium",
        description="Playwright browser engine. Chromium by default (best VFS compatibility).",
    )
    artifact_bucket: str = Field(
        default="voyagent-browser-artifacts",
        description="S3/MinIO bucket for screenshots and DOM snapshots.",
    )
    artifact_endpoint: str | None = Field(
        default=None,
        description="S3-compatible endpoint URL (e.g. MinIO). None -> falls back to in-memory sink.",
    )
    artifact_region: str = Field(
        default="us-east-1",
        description="AWS region for the S3 client. Any string for MinIO.",
    )
    retry_limit: int = Field(
        default=2,
        ge=0,
        description="Maximum retry attempts for a transient failure before marking failed.",
    )
    job_timeout_seconds: int = Field(
        default=180,
        ge=5,
        description="Hard timeout for a single job's handler execution.",
    )
    context_idle_eviction_seconds: int = Field(
        default=600,
        ge=30,
        description="Evict browser contexts that have been idle this long.",
    )


__all__ = ["BrowserRunnerSettings"]
