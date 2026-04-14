"""Database repositories for the in-house auth service.

The repositories are the only layer that touches SQLAlchemy. Routes
call services; services call repositories. Keeping that boundary
clean means tests can swap the storage layer without touching the
HTTP surface.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.storage import RefreshTokenRow, Tenant, User, UserRole

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


__all__ = ["RefreshTokenRepository", "UserRepository"]
