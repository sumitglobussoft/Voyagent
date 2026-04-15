"""Database repositories for the in-house auth service.

The repositories are the only layer that touches SQLAlchemy. Routes
call services; services call repositories. Keeping that boundary
clean means tests can swap the storage layer without touching the
HTTP surface.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import (
    InviteRow,
    InviteStatusEnum,
    RefreshTokenRow,
    Tenant,
    User,
    UserRole,
)

from .tokens import EmailAlreadyRegisteredError


def _skip_email_verification() -> bool:
    """Honor ``VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION`` for dev/tests."""
    raw = os.environ.get("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class UserRepository:
    """Persistence operations for :class:`User` and :class:`Tenant`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_email(self, email: str) -> User | None:
        """Return the user with this (case-insensitive) email or ``None``."""
        result = await self._session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return the user with this id, or ``None`` if not found."""
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def find_tenant(self, tenant_id: uuid.UUID) -> Tenant | None:
        """Return the tenant with this id, or ``None`` if not found."""
        result = await self._session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def create_user_with_tenant(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        agency_name: str,
    ) -> tuple[User, Tenant]:
        """Atomically create a fresh tenant and its first (owner) user.

        Raises :class:`EmailAlreadyRegisteredError` if the email is in
        use. The whole insert is wrapped in a single transaction; on
        the integrity error the partial tenant insert is rolled back.
        """
        tenant = Tenant(
            display_name=agency_name,
            default_currency="USD",
        )
        self._session.add(tenant)
        try:
            await self._session.flush()
        except IntegrityError as exc:  # pragma: no cover - defensive
            await self._session.rollback()
            raise EmailAlreadyRegisteredError("tenant_insert_failed") from exc

        user = User(
            tenant_id=tenant.id,
            # ``external_id`` is a legacy IdP-issued identifier stored as an
            # opaque ``String(128)``; it is surfaced downstream only as
            # ``TenantContext.(user_)external_id: str`` (plain string, not
            # ``EntityId``). UUIDv4 is intentional — this column is not
            # canonical-``EntityId`` territory, so v7 is not required here.
            external_id=str(uuid.uuid4()),
            display_name=full_name,
            email=email.lower(),
            role=UserRole.AGENCY_ADMIN,
            password_hash=password_hash,
            email_verified=_skip_email_verification(),
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError("email_already_registered") from exc

        await self._session.commit()
        await self._session.refresh(user)
        await self._session.refresh(tenant)
        return user, tenant

    async def update_last_login(self, user_id: uuid.UUID) -> None:
        """Record a successful login on the user row."""
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def mark_email_verified(self, user_id: uuid.UUID) -> None:
        """Flip ``email_verified`` to True for a given user."""
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(email_verified=True)
        )
        await self._session.commit()

    async def update_profile(
        self,
        *,
        user_id: uuid.UUID,
        full_name: str | None,
        email: str | None,
    ) -> tuple[User, bool]:
        """Patch ``display_name`` / ``email`` on a user row.

        Returns ``(user, email_changed)``. When the email changes the
        caller is responsible for flipping ``email_verified=False`` — we
        do it here atomically so the caller always sees a consistent
        state. Raises :class:`EmailAlreadyRegisteredError` when the new
        email collides with another account.
        """
        current = await self.find_by_id(user_id)
        if current is None:
            raise EmailAlreadyRegisteredError("user_not_found")

        values: dict[str, object] = {}
        email_changed = False
        if full_name is not None and full_name != current.display_name:
            values["display_name"] = full_name
        if email is not None:
            normalized = email.lower()
            if normalized != current.email:
                other = (
                    await self._session.execute(
                        select(User).where(User.email == normalized)
                    )
                ).scalar_one_or_none()
                if other is not None and other.id != user_id:
                    raise EmailAlreadyRegisteredError(
                        "email_already_registered"
                    )
                values["email"] = normalized
                values["email_verified"] = False
                email_changed = True

        if values:
            try:
                await self._session.execute(
                    update(User).where(User.id == user_id).values(**values)
                )
                await self._session.commit()
            except IntegrityError as exc:
                await self._session.rollback()
                raise EmailAlreadyRegisteredError(
                    "email_already_registered"
                ) from exc

        user = await self.find_by_id(user_id)
        assert user is not None
        return user, email_changed

    async def update_password_hash(
        self, user_id: uuid.UUID, password_hash: str
    ) -> None:
        """Overwrite the password hash for a user."""
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash)
        )
        await self._session.commit()

    async def create_user_in_existing_tenant(
        self,
        *,
        tenant_id: uuid.UUID,
        email: str,
        full_name: str,
        password_hash: str,
        role: str,
    ) -> User:
        """Create a user row attached to an *existing* tenant.

        Used by the accept-invite flow. Unlike
        :meth:`create_user_with_tenant` this does not mint a new
        :class:`Tenant` row — that is the contract change the invite
        subsystem requires.
        """
        try:
            role_enum = UserRole(role)
        except ValueError as exc:
            raise EmailAlreadyRegisteredError("invalid_role") from exc

        user = User(
            tenant_id=tenant_id,
            external_id=str(uuid.uuid4()),
            display_name=full_name,
            email=email.lower(),
            role=role_enum,
            password_hash=password_hash,
            email_verified=_skip_email_verification(),
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError("email_already_registered") from exc
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def list_tenant_members(self, tenant_id: uuid.UUID) -> list[User]:
        """Return every user attached to ``tenant_id``, oldest first."""
        result = await self._session.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.asc())
        )
        return list(result.scalars().all())


class InviteRepository:
    """Persistence operations for :class:`InviteRow`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_pending_for_email(
        self, tenant_id: uuid.UUID, email: str
    ) -> InviteRow | None:
        """Return an existing *pending* invite for ``(tenant, email)``."""
        result = await self._session.execute(
            select(InviteRow).where(
                InviteRow.tenant_id == tenant_id,
                func.lower(InviteRow.email) == email.lower(),
                InviteRow.status == InviteStatusEnum.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        invited_by_user_id: uuid.UUID,
        email: str,
        role: str,
        token_hash: str,
        ttl_days: int = 7,
    ) -> InviteRow:
        """Insert a new pending invite row."""
        expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
        row = InviteRow(
            tenant_id=tenant_id,
            invited_by_user_id=invited_by_user_id,
            email=email.lower(),
            role=role,
            token_hash=token_hash,
            status=InviteStatusEnum.PENDING,
            expires_at=expires,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegisteredError("invite_already_exists") from exc
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def list_for_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        status: InviteStatusEnum | None = None,
    ) -> list[InviteRow]:
        """Return invites for ``tenant_id``, newest first."""
        stmt = select(InviteRow).where(InviteRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(InviteRow.status == status)
        stmt = stmt.order_by(InviteRow.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_id(
        self, invite_id: uuid.UUID
    ) -> InviteRow | None:
        """Return the invite with this id, or ``None``."""
        result = await self._session.execute(
            select(InviteRow).where(InviteRow.id == invite_id)
        )
        return result.scalar_one_or_none()

    async def find_by_token_hash(
        self, token_hash: str
    ) -> InviteRow | None:
        """Return the invite with this ``token_hash``, or ``None``."""
        result = await self._session.execute(
            select(InviteRow).where(InviteRow.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, invite_id: uuid.UUID) -> None:
        """Mark an invite revoked. Idempotent."""
        await self._session.execute(
            update(InviteRow)
            .where(InviteRow.id == invite_id)
            .values(
                status=InviteStatusEnum.REVOKED,
                revoked_at=datetime.now(timezone.utc),
            )
        )
        await self._session.commit()

    async def mark_accepted(self, invite_id: uuid.UUID) -> None:
        """Mark an invite accepted."""
        await self._session.execute(
            update(InviteRow)
            .where(InviteRow.id == invite_id)
            .values(
                status=InviteStatusEnum.ACCEPTED,
                accepted_at=datetime.now(timezone.utc),
            )
        )
        await self._session.commit()


class RefreshTokenRepository:
    """Persistence operations for :class:`RefreshTokenRow`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: bytes,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> None:
        """Insert a new refresh token row."""
        row = RefreshTokenRow(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(row)
        await self._session.commit()

    async def find_active(self, token_hash: bytes) -> RefreshTokenRow | None:
        """Return the row for ``token_hash`` if it is unexpired and not revoked."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(RefreshTokenRow).where(
                RefreshTokenRow.token_hash == token_hash,
                RefreshTokenRow.revoked_at.is_(None),
                RefreshTokenRow.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token_hash: bytes) -> None:
        """Mark a refresh token as revoked. Idempotent."""
        await self._session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.token_hash == token_hash)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token for a user."""
        await self._session.execute(
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def cleanup_expired(self) -> int:
        """Hard-delete expired refresh-token rows. Returns affected count."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            delete(RefreshTokenRow).where(RefreshTokenRow.expires_at <= now)
        )
        await self._session.commit()
        return int(result.rowcount or 0)


__all__ = [
    "InviteRepository",
    "RefreshTokenRepository",
    "UserRepository",
]
