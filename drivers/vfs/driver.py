"""The VFS driver — satisfies :class:`VisaPortalDriver`.

Everything interesting happens in the browser-runner service. This
module is a translation layer:

* canonical call -> :class:`Job` submitted via :class:`BrowserRunnerClient`,
* :class:`JobResult` -> canonical return value OR :class:`DriverError`.

Intentionally thin. When a new portal (BLS, embassy-X) lands, copy this
module, swap the :class:`JobKind` values, and adjust the output mappers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar

from drivers._contracts.errors import (
    ConflictError,
    PermanentError,
    ValidationFailedError,
)
from drivers._contracts.manifest import CapabilityManifest
from schemas.canonical import (
    CountryCode,
    EntityId,
    LocalizedText,
    Passenger,
    Period,
    VisaChecklistItem,
    VisaStatus,
)
from voyagent_browser_runner import BrowserRunnerClient, JobKind, JobResult, JobStatus

from .config import VFSConfig
from .errors import DRIVER_NAME, map_vfs_error

logger = logging.getLogger(__name__)


def _new_entity_id() -> EntityId:
    """UUIDv7-shaped id; mirrors the pattern in other drivers."""
    raw = uuid.uuid4().int
    raw &= ~(0xF << 76)
    raw |= 0x7 << 76
    raw &= ~(0xC << 62)
    raw |= 0x8 << 62
    return str(uuid.UUID(int=raw))


def _raise_if_failed(result: JobResult) -> dict[str, Any]:
    """Return ``outputs`` for a successful result, else raise the driver error."""
    if result.status == JobStatus.SUCCEEDED and result.outputs is not None:
        return result.outputs
    raise map_vfs_error(result.error, artifact_uris=result.artifact_uris)


class VFSDriver:
    """Reference :class:`VisaPortalDriver` implementation.

    All capability-level methods partial because:

    * **Selectors are tenant-configurable.** The runner ships
      placeholder selectors; real VFS deployments require per-tenant
      overrides before any method actually works against production
      pages.
    * **Login gating is unpredictable.** VFS pages intermittently
      surface CAPTCHA and MFA challenges; the driver will raise
      :class:`PermanentError` when it hits those, because the solve
      belongs to a human, not the runner.
    * **Idempotency is portal-dependent.** `book_appointment` is
      explicitly non-idempotent (see the Protocol docstring). We do
      not retry it transparently.
    """

    name: ClassVar[str] = DRIVER_NAME
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        runner: BrowserRunnerClient,
        config: VFSConfig,
        *,
        tenant_id: EntityId | None = None,
    ) -> None:
        self._runner = runner
        self._config = config
        self._tenant_id: EntityId = tenant_id or _new_entity_id()

    async def aclose(self) -> None:
        """No-op. The :class:`BrowserRunnerClient` owns its lifecycle."""
        return None

    # ------------------------------------------------------------------ #
    # Driver protocol                                                    #
    # ------------------------------------------------------------------ #

    def manifest(self) -> CapabilityManifest:
        return CapabilityManifest(
            driver=self.name,
            version=self.version,
            implements=["VisaPortalDriver"],
            capabilities={
                "prepare_checklist": "partial",
                "fill_form": "partial",
                "upload_document": "partial",
                "book_appointment": "partial",
                "read_status": "partial",
            },
            transport=["browser"],
            requires=["browser_runner", "tenant_credentials"],
            tenant_config_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["credentials_ref"],
                "properties": {
                    "destination_country": {
                        "type": "string",
                        "pattern": "^[A-Z]{2}$",
                    },
                    "credentials_ref": {"type": "string", "minLength": 1},
                    "selector_pack_version": {"type": "string"},
                },
                "additionalProperties": True,
            },
        )

    # ------------------------------------------------------------------ #
    # VisaPortalDriver                                                   #
    # ------------------------------------------------------------------ #

    async def prepare_checklist(
        self,
        destination: CountryCode,
        category: str,
        passenger: Passenger,
    ) -> list[VisaChecklistItem]:
        inputs = {
            "destination_country": destination,
            "visa_category": category,
            "passenger_id": getattr(passenger, "id", None),
        }
        result = await self._submit(JobKind.VFS_CHECKLIST_PREPARE, inputs)
        outputs = _raise_if_failed(result)

        items_raw = outputs.get("items") or []
        checklist: list[VisaChecklistItem] = []
        for raw in items_raw:
            if not isinstance(raw, dict):
                continue
            try:
                checklist.append(VisaChecklistItem(**raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "vfs.prepare_checklist.item_parse_failed",
                    extra={"raw": raw, "error": type(exc).__name__},
                )
        return checklist

    async def fill_form(
        self,
        visa_file_id: EntityId,
        field_values: dict[str, Any],
    ) -> None:
        inputs = {
            "visa_file_id": visa_file_id,
            "field_values": field_values,
            "destination_country": self._config.destination_country,
        }
        result = await self._submit(JobKind.VFS_FILL_FORM, inputs)
        _raise_if_failed(result)

    async def upload_document(
        self,
        visa_file_id: EntityId,
        document_id: EntityId,
    ) -> None:
        # NOTE: the runner expects ``local_path`` — this driver's caller
        # (agent runtime) is responsible for materialising the document
        # blob to a path the worker can read. v0 leaves that plumbing to
        # the runtime; this method signature matches the Protocol exactly.
        inputs = {
            "visa_file_id": visa_file_id,
            "document_id": document_id,
            "destination_country": self._config.destination_country,
        }
        result = await self._submit(JobKind.VFS_UPLOAD_DOCUMENT, inputs)
        _raise_if_failed(result)

    async def book_appointment(
        self,
        visa_file_id: EntityId,
        preferred_window: Period,
    ) -> datetime:
        inputs = {
            "visa_file_id": visa_file_id,
            "preferred_window": {
                "start": preferred_window.start.isoformat(),
                "end": preferred_window.end.isoformat()
                if preferred_window.end is not None
                else None,
            },
            "destination_country": self._config.destination_country,
        }
        result = await self._submit(JobKind.VFS_BOOK_APPOINTMENT, inputs)
        outputs = _raise_if_failed(result)
        raw = outputs.get("appointment_at")
        if not isinstance(raw, str):
            raise PermanentError(
                self.name,
                "VFS book_appointment: runner did not return an appointment_at.",
            )
        return datetime.fromisoformat(raw).astimezone(timezone.utc)

    async def read_status(self, application_ref: str) -> VisaStatus:
        inputs = {
            "application_ref": application_ref,
            "destination_country": self._config.destination_country,
        }
        result = await self._submit(JobKind.VFS_READ_STATUS, inputs)
        outputs = _raise_if_failed(result)
        raw = outputs.get("status")
        if not isinstance(raw, str):
            raise PermanentError(
                self.name,
                "VFS read_status: runner did not return a canonical status.",
            )
        try:
            return VisaStatus(raw)
        except ValueError as exc:
            raise ValidationFailedError(
                self.name,
                f"VFS read_status: unexpected status value {raw!r}.",
            ) from exc

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    async def _submit(self, kind: JobKind, inputs: dict[str, Any]) -> JobResult:
        return await self._runner.submit(
            kind,
            inputs,
            tenant_id=self._tenant_id,
            tenant_credentials_ref=self._config.credentials_ref,
            timeout_s=self._config.job_timeout_seconds,
        )


__all__ = ["VFSDriver"]
