from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.oauth_credential import OAuthCredential


class OAuthCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> OAuthCredential | None:
        result = await self._session.execute(
            select(OAuthCredential).where(OAuthCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: int,
        encrypted_refresh_token: bytes,
        encrypted_access_token: bytes,
        token_expires_at: datetime,
        calendar_id: str = "primary",
    ) -> OAuthCredential:
        """Insert a new credential row or replace the existing one for this user."""
        existing = await self.get_by_user_id(user_id)
        if existing is not None:
            existing.encrypted_refresh_token = encrypted_refresh_token
            existing.encrypted_access_token = encrypted_access_token
            existing.token_expires_at = token_expires_at
            existing.calendar_id = calendar_id
            await self._session.flush()
            return existing

        cred = OAuthCredential(
            user_id=user_id,
            provider="google",
            encrypted_refresh_token=encrypted_refresh_token,
            encrypted_access_token=encrypted_access_token,
            token_expires_at=token_expires_at,
            calendar_id=calendar_id,
        )
        self._session.add(cred)
        await self._session.flush()
        await self._session.refresh(cred)
        return cred

    async def update_tokens(
        self,
        user_id: int,
        encrypted_access_token: bytes,
        token_expires_at: datetime,
    ) -> OAuthCredential | None:
        """Overwrite only the access token and its expiry (after a token refresh)."""
        cred = await self.get_by_user_id(user_id)
        if cred is None:
            return None
        cred.encrypted_access_token = encrypted_access_token
        cred.token_expires_at = token_expires_at
        await self._session.flush()
        return cred

    async def delete_by_user_id(self, user_id: int) -> bool:
        cred = await self.get_by_user_id(user_id)
        if cred is None:
            return False
        await self._session.delete(cred)
        await self._session.flush()
        return True

    async def get_expiring_soon(self, within_seconds: int = 300) -> list[OAuthCredential]:
        """Return credentials whose access token expires within *within_seconds*."""
        threshold = datetime.now(UTC) + timedelta(seconds=within_seconds)
        result = await self._session.execute(
            select(OAuthCredential).where(OAuthCredential.token_expires_at <= threshold)
        )
        return list(result.scalars().all())
