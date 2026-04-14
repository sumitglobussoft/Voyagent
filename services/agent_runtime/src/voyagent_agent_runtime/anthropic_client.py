"""Anthropic SDK wrapper with prompt caching baked in.

All runtime components talk to Anthropic through :class:`AnthropicClient`
rather than importing the SDK directly. This keeps a narrow seam for
testing (swap a fake client in) and centralises cache-control tagging.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS = 1024


class Settings(BaseSettings):
    """Runtime-level settings loaded from the environment.

    The Anthropic key is the one exception to the ``VOYAGENT_`` prefix —
    the upstream SDK uses ``ANTHROPIC_API_KEY`` and we follow suit so
    tooling works without redirection.
    """

    model_config = SettingsConfigDict(
        env_prefix="VOYAGENT_",
        case_sensitive=False,
        extra="ignore",
    )

    agent_model: str = Field(default=DEFAULT_MODEL)
    agent_max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=64, le=16384)
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="ANTHROPIC_API_KEY",
    )


class _AnthropicLike(Protocol):
    """Minimal protocol the wrapper needs from ``anthropic.AsyncAnthropic``.

    We declare just the surface we call so tests can stub with a plain
    object that implements ``messages.stream`` and ``close``.
    """

    messages: Any

    async def close(self) -> None: ...


class AnthropicClient:
    """Async wrapper that streams Anthropic ``messages`` responses.

    Enables prompt caching by wrapping the last system block and the
    tools array with ``cache_control = {"type": "ephemeral"}``. Callers
    pass plain strings/dicts and the client does the tagging.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: _AnthropicLike | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._client = client
        self._owns_client = client is None

    @property
    def model(self) -> str:
        return self._settings.agent_model

    @property
    def settings(self) -> Settings:
        return self._settings

    def _ensure_client(self) -> _AnthropicLike:
        """Lazily build the underlying SDK client.

        We import inside the method so the module is importable in
        environments without the anthropic wheel (e.g. some test shards).
        """
        if self._client is None:
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

            key = self._settings.anthropic_api_key.get_secret_value()
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set; cannot call Anthropic."
                )
            self._client = AsyncAnthropic(api_key=key)
        return self._client

    @staticmethod
    def _build_system_blocks(system: str) -> list[dict[str, Any]]:
        """Shape ``system`` into the block-form the SDK accepts and tag for caching."""
        return [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    @staticmethod
    def _tag_tools_for_cache(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach ephemeral cache_control to the last tool so the whole tool
        array shares a cache breakpoint."""
        if not tools:
            return tools
        tagged = [dict(t) for t in tools]
        tagged[-1] = {**tagged[-1], "cache_control": {"type": "ephemeral"}}
        return tagged

    async def stream_messages(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[Any]:
        """Stream an Anthropic ``messages`` response.

        Yields whatever event objects the SDK yields; callers typically
        branch on ``event.type`` for ``content_block_delta``, ``content_block_start``,
        ``message_stop``, etc. Prompt caching is enabled on system + tools.
        """
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens or self._settings.agent_max_tokens,
            "system": self._build_system_blocks(system),
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = self._tag_tools_for_cache(tools)

        # Never log message bodies at INFO — only model + counts.
        logger.debug(
            "anthropic.messages.stream model=%s tools=%d msgs=%d",
            kwargs["model"],
            len(kwargs.get("tools") or []),
            len(messages),
        )

        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                yield event

    async def ping(self) -> bool:
        """Cheap smoke-test: confirm the client can be built."""
        try:
            self._ensure_client()
        except RuntimeError:
            return False
        return True

    async def aclose(self) -> None:
        """Release the underlying SDK client, if we own it."""
        if self._client is not None and self._owns_client:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                logger.exception("anthropic client close failed")
            self._client = None


__all__ = ["AnthropicClient", "Settings", "DEFAULT_MODEL"]
