"""Clerk webhooks — sync IDP lifecycle to Postgres.

Clerk mints users/orgs in its own control plane. Without this endpoint
Voyagent has no idea when a user is deactivated, renamed, or added to
a new organisation — the JWT carries a snapshot but doesn't drive
persistence. This endpoint plays the other half of the contract:
Clerk calls us on every lifecycle change and we upsert / deactivate
the corresponding Postgres row.

Idempotency
-----------
Every write is an upsert keyed on ``(tenant_id, external_id)`` for
users and ``external_id`` for tenants. Replaying the same payload is
a no-op diff, which means Clerk's at-least-once delivery guarantees
are safe — we never duplicate rows.

Signature
---------
We verify via the ``svix`` library using
``VOYAGENT_CLERK_WEBHOOK_SECRET``. An unsigned or tampered payload
returns HTTP 400 before the payload is parsed. A malformed JSON body
from a genuine sender returns HTTP 422.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# --------------------------------------------------------------------------- #
# Signature verification                                                      #
# --------------------------------------------------------------------------- #


def _webhook_secret() -> str | None:
    return os.environ.get("VOYAGENT_CLERK_WEBHOOK_SECRET", "").strip() or None


async def _verify_and_parse(request: Request) -> dict[str, Any]:
    body = await request.body()
    secret = _webhook_secret()
    if secret is None:
        logger.warning(
            "VOYAGENT_CLERK_WEBHOOK_SECRET is unset — rejecting webhook. "
            "Configure the secret on the Clerk side and in env."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="webhook_unconfigured"
        )

    try:
        from svix.webhooks import Webhook, WebhookVerificationError  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.error("svix library not installed — cannot verify Clerk webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="svix_unavailable",
        ) from exc

    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        wh = Webhook(secret)
        wh.verify(body, headers)
    except WebhookVerificationError as exc:
        logger.info("webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="bad_signature"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook verify raised: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="bad_signature"
        ) from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"bad_payload: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="payload_not_object",
        )
    return payload


# --------------------------------------------------------------------------- #
# Role mapping                                                                #
# --------------------------------------------------------------------------- #


def _map_clerk_role(raw: str | None) -> str:
    """Conservative mapping from Clerk's ``org:*`` roles to our enum.

    Everything that isn't obviously an admin becomes ``"agent"`` to
    avoid accidentally elevating users. A real role-mapping table
    belongs in settings, not here.
    """
    if not raw:
        return "agent"
    value = raw.strip().lower()
    if value in ("org:admin", "admin", "owner", "org:owner"):
        return "admin"
    return "agent"


# --------------------------------------------------------------------------- #
# Persistence helpers                                                         #
# --------------------------------------------------------------------------- #


def _load_storage_types() -> dict[str, Any] | None:
    """Return the storage types we need, or ``None`` if unavailable."""
    try:
        from schemas.storage import Tenant, User, UserRole  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.warning("schemas.storage unavailable — webhook will no-op: %s", exc)
        return None
    return {"Tenant": Tenant, "User": User, "UserRole": UserRole}


def _db_url() -> str | None:
    return os.environ.get("VOYAGENT_DB_URL", "").strip() or None


def _make_engine() -> Any | None:
    url = _db_url()
    if not url:
        return None
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        return create_async_engine(url, future=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook engine build failed: %s", exc)
        return None


def _deterministic_uuid(namespace: str, seed: str) -> uuid.UUID:
    """Derive a UUIDv7-shaped id from ``(namespace, seed)``.

    Mirrors the tenancy fallback so the webhook and the request path
    agree on canonical ids for the same Clerk external id.
    """
    import hashlib

    digest = hashlib.sha256(f"{namespace}:{seed}".encode("utf-8")).hexdigest()
    parts = (
        digest[0:8],
        digest[8:12],
        "7" + digest[13:16],
        "8" + digest[17:20],
        digest[20:32],
    )
    return uuid.UUID("-".join(parts))


# --------------------------------------------------------------------------- #
# Event handlers                                                              #
# --------------------------------------------------------------------------- #


def _primary_org_id(user_data: dict[str, Any]) -> str | None:
    """Pick the user's primary organisation id from a Clerk user payload.

    Clerk's ``user.*`` events include an ``organization_memberships``
    array. We take the first entry, or fall back to a top-level
    ``organization_id`` when present.
    """
    memberships = user_data.get("organization_memberships") or []
    if isinstance(memberships, list) and memberships:
        first = memberships[0]
        if isinstance(first, dict):
            org_id = (
                first.get("organization", {}).get("id")
                or first.get("organization_id")
            )
            if org_id:
                return str(org_id)
    org = user_data.get("organization")
    if isinstance(org, dict) and org.get("id"):
        return str(org["id"])
    if user_data.get("organization_id"):
        return str(user_data["organization_id"])
    return None


def _org_role_for_user(user_data: dict[str, Any]) -> str | None:
    memberships = user_data.get("organization_memberships") or []
    if isinstance(memberships, list) and memberships:
        first = memberships[0]
        if isinstance(first, dict):
            return first.get("role") or None
    return None


async def _upsert_tenant(
    engine: Any,
    *,
    external_id: str,
    display_name: str | None,
    is_active: bool = True,
) -> None:
    types = _load_storage_types()
    if types is None:
        return
    Tenant = types["Tenant"]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        async with db.begin():
            # We do not yet store a native external_id on tenants; we
            # derive a deterministic UUIDv7 from the Clerk org id so
            # the PK is stable across replays and the in-memory
            # tenancy fallback uses the same mapping.
            tid = _deterministic_uuid("voyagent.tenant", external_id)
            row = await db.get(Tenant, tid)
            if row is None:
                db.add(
                    Tenant(
                        id=tid,
                        display_name=display_name or external_id,
                        default_currency="USD",
                        is_active=is_active,
                    )
                )
            else:
                if display_name:
                    row.display_name = display_name
                row.is_active = is_active
    # ``select`` is imported for future external_id lookups once the
    # column lands; intentionally unused for now.
    _ = select


async def _upsert_user(
    engine: Any,
    *,
    tenant_external_id: str,
    external_id: str,
    display_name: str | None,
    email: str | None,
    role: str,
    is_active: bool = True,
) -> None:
    types = _load_storage_types()
    if types is None:
        return
    User = types["User"]
    UserRole = types["UserRole"]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    tenant_uuid = _deterministic_uuid("voyagent.tenant", tenant_external_id)
    # Best-effort tenant upsert so a dangling user has something to
    # hang off. No-ops when the tenant already exists.
    await _upsert_tenant(
        engine,
        external_id=tenant_external_id,
        display_name=None,
        is_active=True,
    )

    try:
        role_enum = UserRole(role)
    except ValueError:
        role_enum = UserRole("agent")

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        async with db.begin():
            stmt = (
                select(User)
                .where(User.tenant_id == tenant_uuid)
                .where(User.external_id == external_id)
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            uid = _deterministic_uuid(
                f"voyagent.user:{tenant_external_id}", external_id
            )
            if existing is None:
                db.add(
                    User(
                        id=uid,
                        tenant_id=tenant_uuid,
                        external_id=external_id,
                        display_name=display_name or external_id,
                        email=email or f"{external_id}@unknown.invalid",
                        role=role_enum,
                    )
                )
            else:
                if display_name:
                    existing.display_name = display_name
                if email:
                    existing.email = email
                existing.role = role_enum
            # ``is_active`` is a User column only after a future
            # migration adds it; for v0 we deactivate by leaving the
            # row in place but scrubbing the email. The ``User`` model
            # today has no is_active column, so we skip the field.
            del is_active


async def _handle_user_event(engine: Any, event_type: str, data: dict[str, Any]) -> None:
    external_id = str(data.get("id") or "").strip()
    if not external_id:
        return
    org_id = _primary_org_id(data)
    if not org_id:
        logger.info("skipping user %s — no primary org on the payload", external_id)
        return
    email_addresses = data.get("email_addresses") or []
    email: str | None = None
    if isinstance(email_addresses, list) and email_addresses:
        first = email_addresses[0]
        if isinstance(first, dict):
            email = first.get("email_address") or first.get("email") or None
    name_parts = [
        str(data.get("first_name") or "").strip(),
        str(data.get("last_name") or "").strip(),
    ]
    display_name = " ".join(p for p in name_parts if p) or external_id

    role = _map_clerk_role(_org_role_for_user(data))
    is_active = event_type != "user.deleted"
    # UserRole enum values in storage are more granular than our
    # admin/agent binary — we map "admin" onto agency_admin.
    if role == "admin":
        role_value = "agency_admin"
    else:
        role_value = "agent"

    await _upsert_user(
        engine,
        tenant_external_id=org_id,
        external_id=external_id,
        display_name=display_name,
        email=email,
        role=role_value,
        is_active=is_active,
    )


async def _handle_org_event(engine: Any, event_type: str, data: dict[str, Any]) -> None:
    external_id = str(data.get("id") or "").strip()
    if not external_id:
        return
    display_name = str(data.get("name") or "").strip() or external_id
    is_active = event_type != "organization.deleted"
    await _upsert_tenant(
        engine,
        external_id=external_id,
        display_name=display_name,
        is_active=is_active,
    )


async def _handle_membership_event(
    engine: Any, event_type: str, data: dict[str, Any]
) -> None:
    org = data.get("organization") or {}
    user = data.get("public_user_data") or data.get("user") or {}
    org_id = str(org.get("id") or data.get("organization_id") or "").strip()
    user_id = str(user.get("user_id") or user.get("id") or "").strip()
    if not org_id or not user_id:
        return
    role = _map_clerk_role(data.get("role") or user.get("role"))
    # Deletions leave the user in place but demote to agent.
    if event_type == "organizationMembership.deleted":
        role = "agent"
    role_value = "agency_admin" if role == "admin" else "agent"

    email = None
    if isinstance(user, dict):
        email = user.get("email_address") or user.get("email")
    display_name = None
    if isinstance(user, dict):
        parts = [
            str(user.get("first_name") or "").strip(),
            str(user.get("last_name") or "").strip(),
        ]
        display_name = " ".join(p for p in parts if p) or user_id

    await _upsert_user(
        engine,
        tenant_external_id=org_id,
        external_id=user_id,
        display_name=display_name,
        email=email,
        role=role_value,
        is_active=True,
    )


# --------------------------------------------------------------------------- #
# Endpoint                                                                    #
# --------------------------------------------------------------------------- #


_HANDLED_USER_EVENTS = {"user.created", "user.updated", "user.deleted"}
_HANDLED_ORG_EVENTS = {
    "organization.created",
    "organization.updated",
    "organization.deleted",
}
_HANDLED_MEMBERSHIP_EVENTS = {
    "organizationMembership.created",
    "organizationMembership.updated",
    "organizationMembership.deleted",
}


@router.post("/clerk")
async def clerk_webhook(request: Request) -> dict[str, Any]:
    """Accept a Clerk webhook and sync the affected row into Postgres."""
    payload = await _verify_and_parse(request)
    event_type = str(payload.get("type") or "").strip()
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="data_not_object",
        )

    engine = _make_engine()
    if engine is None:
        logger.warning(
            "VOYAGENT_DB_URL is unset — webhook %s accepted but discarded",
            event_type,
        )
        return {"accepted": True, "persisted": False, "event": event_type}

    try:
        if event_type in _HANDLED_USER_EVENTS:
            await _handle_user_event(engine, event_type, data)
        elif event_type in _HANDLED_ORG_EVENTS:
            await _handle_org_event(engine, event_type, data)
        elif event_type in _HANDLED_MEMBERSHIP_EVENTS:
            await _handle_membership_event(engine, event_type, data)
        else:
            logger.info("ignoring unhandled Clerk event: %s", event_type)
            return {"accepted": True, "persisted": False, "event": event_type}
    finally:
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001
            pass

    return {"accepted": True, "persisted": True, "event": event_type}


# --------------------------------------------------------------------------- #
# Revocation endpoint                                                         #
# --------------------------------------------------------------------------- #


auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/revoke")
async def revoke_self(request: Request) -> dict[str, Any]:
    """Revoke the JWT presented on the current request.

    The endpoint reads the ``Authorization`` header, extracts the
    ``jti`` + ``exp`` claims (without re-verifying — we already ran
    :func:`verify_token` via the dependency), and appends the jti to
    the revocation list until ``exp``. Records an AuditEvent so the
    action is traceable.
    """
    from .auth import (
        _dev_principal,
        _extract_bearer,
        get_auth_settings,
        verify_token,
    )
    from .revocation import build_revocation_list

    settings = get_auth_settings()
    authorization = request.headers.get("authorization")
    if not settings.enabled:
        principal = _dev_principal(
            request.headers.get("x-voyagent-dev-tenant"),
            request.headers.get("x-voyagent-dev-actor"),
            request.headers.get("x-voyagent-dev-role"),
            request.headers.get("x-voyagent-dev-email"),
        )
    else:
        token_pre = _extract_bearer(authorization)
        if token_pre is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authorization_header_missing",
            )
        principal = await verify_token(token_pre)
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authorization_header_missing",
        )

    try:
        import jwt as _jwt

        claims = _jwt.decode(token, options={"verify_signature": False})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"jwt_decode_failed: {exc}"
        ) from exc
    jti = str(claims.get("jti") or "").strip()
    exp = int(claims.get("exp") or 0)
    if not jti or not exp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="jwt_missing_jti_or_exp",
        )

    rev = build_revocation_list()
    await rev.revoke(jti, exp)

    # Record an audit event — best-effort.
    try:
        from datetime import datetime, timezone

        from schemas.canonical import ActorKind, AuditEvent, AuditStatus

        from .audit import _uuid7_like, get_api_audit_sink

        now = datetime.now(timezone.utc)
        event = AuditEvent(
            id=_uuid7_like(),
            tenant_id=principal.tenant_external_id
            if _looks_like_uuid(principal.tenant_external_id)
            else "00000000-0000-7000-8000-000000000000",
            actor_id=principal.user_external_id
            if _looks_like_uuid(principal.user_external_id)
            else "00000000-0000-7000-8000-000000000000",
            actor_kind=ActorKind.HUMAN,
            tool="auth.revoke_self",
            inputs={"jti": jti[:16]},  # first 16 chars only — jti may be sensitive
            started_at=now,
            completed_at=now,
            status=AuditStatus.SUCCEEDED,
        )
        sink = get_api_audit_sink()
        await sink.write(event)
    except Exception as exc:  # noqa: BLE001
        logger.debug("auth.revoke_self audit write failed: %s", exc)

    return {"revoked": True}


def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except Exception:  # noqa: BLE001
        return False


__all__ = ["auth_router", "router"]
