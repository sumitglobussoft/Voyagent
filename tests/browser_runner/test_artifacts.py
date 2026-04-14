"""Tests for :mod:`voyagent_browser_runner.artifacts`.

The in-memory sink is round-tripped directly; the S3 sink is exercised
against a tiny fake boto client (no live network). We assert the bucket
and key layout the runner promises in its docstrings.
"""

from __future__ import annotations

from typing import Any

import pytest

from voyagent_browser_runner.artifacts import (
    InMemoryArtifactSink,
    S3ArtifactSink,
    build_artifact_sink,
)


# --------------------------------------------------------------------------- #
# build_artifact_sink selection                                               #
# --------------------------------------------------------------------------- #


def test_build_artifact_sink_without_endpoint_is_in_memory() -> None:
    sink = build_artifact_sink(
        bucket="voyagent-artifacts", endpoint_url=None, region="us-east-1"
    )
    assert isinstance(sink, InMemoryArtifactSink)


# --------------------------------------------------------------------------- #
# InMemoryArtifactSink round-trip                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_in_memory_sink_roundtrips_bytes() -> None:
    sink = InMemoryArtifactSink()

    uri1 = await sink.put(
        "tenant-1/job-9",
        "screenshot.png",
        b"\x89PNG\r\n\x1a\n-fake-png",
        "image/png",
    )
    uri2 = await sink.put(
        "tenant-1/job-9",
        "dom.html",
        b"<html></html>",
        "text/html; charset=utf-8",
    )
    uri3 = await sink.put(
        "tenant-1/job-9",
        "error.txt",
        b"Traceback (most recent call last):\n  File ...",
        "text/plain",
    )

    for uri, expected in [
        (uri1, b"\x89PNG\r\n\x1a\n-fake-png"),
        (uri2, b"<html></html>"),
        (uri3, b"Traceback (most recent call last):\n  File ..."),
    ]:
        assert uri.startswith("memory://")
        data = sink.get(uri)
        assert data is not None
        payload, content_type = data
        assert payload == expected
        assert content_type != ""

    # Distinct filenames produce distinct URIs.
    assert len({uri1, uri2, uri3}) == 3

    await sink.aclose()
    # After close, the store is empty.
    assert sink.get(uri1) is None


@pytest.mark.asyncio
async def test_in_memory_sink_uri_prefix_matches_prefix_arg() -> None:
    """The returned ``memory://`` URI must echo the ``<prefix>/<filename>``."""
    sink = InMemoryArtifactSink()
    uri = await sink.put("tenantX/jobY", "a.png", b"x", "image/png")
    assert uri == "memory://tenantX/jobY/a.png"


# --------------------------------------------------------------------------- #
# S3ArtifactSink — fake boto                                                  #
# --------------------------------------------------------------------------- #


class _FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeS3Client":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> dict[str, Any]:
        self.calls.append(
            {"Bucket": Bucket, "Key": Key, "Body": Body, "ContentType": ContentType}
        )
        return {"ETag": '"fake-etag"'}


class _FakeSession:
    def __init__(self) -> None:
        self.s3 = _FakeS3Client()

    def client(self, name: str, **kwargs: Any) -> _FakeS3Client:
        assert name == "s3"
        return self.s3


@pytest.mark.asyncio
async def test_s3_sink_puts_to_bucket_with_prefix_and_filename_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploaded objects go to ``<bucket>/<prefix>/<filename>`` via aioboto3."""
    import aioboto3  # type: ignore[import-not-found]

    fake_session = _FakeSession()
    monkeypatch.setattr(aioboto3, "Session", lambda: fake_session)

    sink = S3ArtifactSink(
        bucket="voyagent-artifacts",
        endpoint_url="https://minio.local:9000",
        region="us-east-1",
    )

    uri = await sink.put(
        "t-42/j-99", "screenshot.png", b"img-bytes", "image/png"
    )

    # One call, to the right bucket + key.
    assert len(fake_session.s3.calls) == 1
    call = fake_session.s3.calls[0]
    assert call["Bucket"] == "voyagent-artifacts"
    assert call["Key"] == "t-42/j-99/screenshot.png"
    assert call["Body"] == b"img-bytes"
    assert call["ContentType"] == "image/png"

    # Returned URI includes the endpoint for MinIO-style deployments.
    assert uri == "https://minio.local:9000/voyagent-artifacts/t-42/j-99/screenshot.png"

    await sink.aclose()


@pytest.mark.asyncio
async def test_s3_sink_without_endpoint_returns_s3_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an endpoint_url the URI is the canonical ``s3://`` form."""
    import aioboto3  # type: ignore[import-not-found]

    fake_session = _FakeSession()
    monkeypatch.setattr(aioboto3, "Session", lambda: fake_session)

    sink = S3ArtifactSink(
        bucket="voyagent-artifacts", endpoint_url=None, region="us-east-1"
    )
    uri = await sink.put("t/j", "a.txt", b"hello", "text/plain")
    assert uri == "s3://voyagent-artifacts/t/j/a.txt"
