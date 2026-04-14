"""Generic (portal-agnostic) handlers.

Useful for ad-hoc debugging and for smoke-testing that the runner is
reachable from a driver without exercising a full VFS flow.
"""

from __future__ import annotations

from typing import Any

from .. import steps
from . import HandlerContext


async def handle_generic_screenshot(ctx: HandlerContext) -> dict[str, Any]:
    """Navigate to ``inputs['url']`` and return the screenshot URI."""
    url = str(ctx.job.inputs["url"])
    label = str(ctx.job.inputs.get("label", "page"))
    await steps.goto(ctx.page, url)
    uri = await steps.screenshot(
        ctx.page,
        label,
        ctx.artifacts,
        prefix=f"{ctx.tenant_id}/{ctx.job.id}",
    )
    return {"artifact_uri": uri}


async def handle_generic_goto_and_extract(ctx: HandlerContext) -> dict[str, Any]:
    """Navigate to ``inputs['url']`` and return ``text_content(selector)``."""
    url = str(ctx.job.inputs["url"])
    selector = str(ctx.job.inputs["selector"])
    await steps.goto(ctx.page, url)
    text = await steps.extract_text(ctx.page, selector)
    return {"text": text}


__all__ = [
    "handle_generic_goto_and_extract",
    "handle_generic_screenshot",
]
