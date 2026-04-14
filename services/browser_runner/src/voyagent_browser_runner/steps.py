"""Reusable Playwright step primitives.

Every step:

* logs a ``step.started`` / ``step.ended`` / ``step.failed`` event with
  the step name, duration, and safe metadata,
* masks values marked as secret,
* never raises the Playwright exception unwrapped — callers catch at the
  handler level where failure artifacts are captured.

Playwright is imported lazily at call time so unit tests can supply a
duck-typed ``FakePage`` without ever pulling in the real wheel.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from schemas.canonical import EntityId

if TYPE_CHECKING:
    from .artifacts import ArtifactSink

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Logging helpers                                                             #
# --------------------------------------------------------------------------- #


def _redact(value: str, *, mask: bool) -> str:
    """Return a log-safe representation of ``value``."""
    if not mask:
        return value
    if not value:
        return ""
    return f"***({len(value)} chars)"


def _emit(event: str, *, step: str, **extra: Any) -> None:
    """Emit a structured log line. Never lets extras clobber reserved keys."""
    safe = {k: v for k, v in extra.items() if k not in ("msg", "args", "levelname")}
    logger.info(event, extra={"step": step, **safe})


# --------------------------------------------------------------------------- #
# Primitives                                                                  #
# --------------------------------------------------------------------------- #


async def goto(page: Any, url: str, *, timeout_ms: int = 30_000) -> None:
    """Navigate ``page`` to ``url``."""
    started = time.monotonic()
    _emit("step.started", step="goto", url=url)
    try:
        await page.goto(url, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001 — re-raised after logging
        _emit(
            "step.failed",
            step="goto",
            url=url,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    _emit(
        "step.ended",
        step="goto",
        url=url,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def click(page: Any, selector: str, *, timeout_ms: int = 10_000) -> None:
    """Click the first element matching ``selector``."""
    started = time.monotonic()
    _emit("step.started", step="click", selector=selector)
    try:
        await page.click(selector, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="click",
            selector=selector,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    _emit(
        "step.ended",
        step="click",
        selector=selector,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def fill(
    page: Any,
    selector: str,
    value: str,
    *,
    mask: bool = False,
    timeout_ms: int = 10_000,
) -> None:
    """Type ``value`` into the field matching ``selector``.

    When ``mask=True`` the value is redacted in all logs and never
    appears in artifact filenames.
    """
    started = time.monotonic()
    _emit(
        "step.started",
        step="fill",
        selector=selector,
        value=_redact(value, mask=mask),
    )
    try:
        await page.fill(selector, value, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="fill",
            selector=selector,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    _emit(
        "step.ended",
        step="fill",
        selector=selector,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def wait_for(
    page: Any,
    selector: str,
    *,
    state: str = "visible",
    timeout_ms: int = 15_000,
) -> None:
    """Wait until ``selector`` reaches the given ``state``."""
    started = time.monotonic()
    _emit("step.started", step="wait_for", selector=selector, state=state)
    try:
        await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="wait_for",
            selector=selector,
            state=state,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    _emit(
        "step.ended",
        step="wait_for",
        selector=selector,
        state=state,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def upload_file(page: Any, selector: str, path: str) -> None:
    """Attach ``path`` to the file input identified by ``selector``."""
    started = time.monotonic()
    _emit("step.started", step="upload_file", selector=selector, path=path)
    try:
        await page.set_input_files(selector, path)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="upload_file",
            selector=selector,
            path=path,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    _emit(
        "step.ended",
        step="upload_file",
        selector=selector,
        path=path,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def extract_text(page: Any, selector: str, *, timeout_ms: int = 10_000) -> str:
    """Return the text content of the first node matching ``selector``."""
    started = time.monotonic()
    _emit("step.started", step="extract_text", selector=selector)
    try:
        text = await page.text_content(selector, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="extract_text",
            selector=selector,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    value = (text or "").strip()
    _emit(
        "step.ended",
        step="extract_text",
        selector=selector,
        duration_ms=int((time.monotonic() - started) * 1000),
        length=len(value),
    )
    return value


async def screenshot(
    page: Any,
    label: str,
    artifacts: "ArtifactSink",
    *,
    prefix: str = "",
) -> str:
    """Capture a full-page screenshot, push it to ``artifacts``, return the URI.

    ``label`` is used as the filename stem; it must not contain secrets.
    """
    started = time.monotonic()
    _emit("step.started", step="screenshot", label=label)
    try:
        data = await page.screenshot(full_page=True)
    except Exception as exc:  # noqa: BLE001
        _emit(
            "step.failed",
            step="screenshot",
            label=label,
            duration_ms=int((time.monotonic() - started) * 1000),
            error=type(exc).__name__,
        )
        raise
    uri = await artifacts.put(prefix or "misc", f"{label}.png", data, "image/png")
    _emit(
        "step.ended",
        step="screenshot",
        label=label,
        uri=uri,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return uri


async def capture_failure(
    page: Any,
    job_id: EntityId,
    tenant_id: EntityId,
    error: Exception,
    artifacts: "ArtifactSink",
) -> list[str]:
    """Capture a screenshot + HTML snapshot and return their URIs.

    Best-effort: if the page itself is broken we return whatever we
    managed before the second failure. Callers must always write a
    :class:`JobResult` regardless.
    """
    prefix = f"{tenant_id}/{job_id}"
    label = f"failure-{type(error).__name__.lower()}"
    uris: list[str] = []
    try:
        png = await page.screenshot(full_page=True)
        uris.append(
            await artifacts.put(prefix, f"{label}.png", png, "image/png")
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "capture_failure.screenshot_failed",
            extra={"job_id": job_id},
            exc_info=True,
        )
    try:
        html = await page.content()
        uris.append(
            await artifacts.put(
                prefix,
                f"{label}.html",
                html.encode("utf-8"),
                "text/html; charset=utf-8",
            )
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "capture_failure.content_failed",
            extra={"job_id": job_id},
            exc_info=True,
        )
    return uris


__all__ = [
    "capture_failure",
    "click",
    "extract_text",
    "fill",
    "goto",
    "screenshot",
    "upload_file",
    "wait_for",
]
