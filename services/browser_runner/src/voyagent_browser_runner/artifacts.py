"""Artifact persistence for screenshots + DOM snapshots.

The worker always captures a failure artifact before writing a FAILED
:class:`JobResult` — see :func:`steps.capture_failure`. Drivers receive
artifact URIs as opaque strings and typically attach them to a
``DriverError.vendor_ref`` for operator triage.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ArtifactSink(Protocol):
    """Somewhere to park a screenshot or DOM snapshot.

    ``prefix`` is conventionally ``"<tenant_id>/<job_id>"`` so artifacts
    for a single job cluster together in the bucket listing.
    """

    async def put(
        self,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        ...

    async def aclose(self) -> None:
        ...


class InMemoryArtifactSink:
    """Dev / test sink.

    Holds artifacts in a dict keyed by ``<prefix>/<filename>``. A warning
    is logged on construction so a production deployment that accidentally
    falls back here is obvious in logs.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, str]] = {}
        logger.warning(
            "artifacts.in_memory_sink_active",
            extra={
                "note": (
                    "Using InMemoryArtifactSink — artifacts will be lost on "
                    "worker restart. Configure VOYAGENT_BROWSER_ARTIFACT_ENDPOINT "
                    "for persistent storage."
                )
            },
        )

    async def put(
        self,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        key = f"{prefix}/{filename}"
        self._store[key] = (data, content_type)
        return f"memory://{key}"

    def get(self, uri: str) -> tuple[bytes, str] | None:
        """Test-only read-back hook."""
        if uri.startswith("memory://"):
            return self._store.get(uri[len("memory://") :])
        return None

    async def aclose(self) -> None:
        self._store.clear()


class S3ArtifactSink:
    """S3 / MinIO-backed artifact sink.

    Uses ``aioboto3`` so uploads don't block the worker's event loop.
    The caller is responsible for ensuring the bucket exists — a
    production deploy typically provisions it once via Terraform.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str = "us-east-1",
    ) -> None:
        # Imported lazily so tests that only exercise the in-memory sink
        # don't need aioboto3 installed.
        import aioboto3

        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._session = aioboto3.Session()

    async def put(
        self,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        key = f"{prefix}/{filename}"
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
        ) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        if self._endpoint_url:
            return f"{self._endpoint_url.rstrip('/')}/{self._bucket}/{key}"
        return f"s3://{self._bucket}/{key}"

    async def aclose(self) -> None:
        # aioboto3 session has no explicit close; each client is
        # short-lived and closes via its async context manager.
        return None


def build_artifact_sink(
    *,
    bucket: str,
    endpoint_url: str | None,
    region: str = "us-east-1",
) -> ArtifactSink:
    """Pick an artifact sink based on whether an endpoint is configured."""
    if endpoint_url is None:
        return InMemoryArtifactSink()
    return S3ArtifactSink(bucket=bucket, endpoint_url=endpoint_url, region=region)


__all__ = [
    "ArtifactSink",
    "InMemoryArtifactSink",
    "S3ArtifactSink",
    "build_artifact_sink",
]
