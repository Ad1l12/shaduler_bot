import asyncio
from datetime import UTC, datetime
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.repositories.oauth_credential_repo import OAuthCredentialRepository
from src.exceptions import GoogleApiError
from src.security.encryption import decrypt_token, encrypt_token

_SCOPES = ["https://www.googleapis.com/auth/calendar"]

_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _client_config() -> dict[str, Any]:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": _TOKEN_URI,
        }
    }


def _make_flow() -> Flow:
    flow: Flow = Flow.from_client_config(_client_config(), scopes=_SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def _ensure_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = OAuthCredentialRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_auth_url(self, user_id: int) -> str:
        """Build the Google OAuth consent URL with state=user_id."""
        flow = _make_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=str(user_id),
            prompt="consent",  # Always request refresh_token
        )
        return str(auth_url)

    async def handle_callback(self, code: str, state: str) -> bool:
        """Exchange the authorisation code for tokens and persist them.

        Returns True on success, False when the state is invalid or Google
        did not return a refresh_token (user revoked offline access).
        Raises GoogleApiError on network / API failures.
        """
        try:
            user_id = int(state)
        except ValueError:
            return False

        flow = _make_flow()
        try:
            await asyncio.to_thread(flow.fetch_token, code=code)
        except Exception as exc:
            raise GoogleApiError(f"Failed to exchange OAuth code: {exc}") from exc

        creds: Credentials = flow.credentials

        if not creds.refresh_token or not creds.token or not creds.expiry:
            return False

        await self._repo.upsert(
            user_id=user_id,
            encrypted_refresh_token=encrypt_token(creds.refresh_token),
            encrypted_access_token=encrypt_token(creds.token),
            token_expires_at=_ensure_utc(creds.expiry),
        )
        return True

    async def get_valid_token(self, user_id: int) -> str | None:
        """Return a valid access_token, refreshing it transparently if expired.

        Returns None if the user has no credentials or the refresh_token is
        invalid (credentials are deleted in that case so the user must re-auth).
        Raises GoogleApiError on unexpected network failures.
        """
        cred_row = await self._repo.get_by_user_id(user_id)
        if cred_row is None:
            return None

        now = datetime.now(UTC)

        if cred_row.token_expires_at > now:
            return decrypt_token(cred_row.encrypted_access_token)

        # Access token expired — refresh via refresh_token
        try:
            refresh_token = decrypt_token(cred_row.encrypted_refresh_token)
        except Exception:
            # Corrupted credential — clean up
            await self._repo.delete_by_user_id(user_id)
            return None

        creds = Credentials(  # type: ignore[no-untyped-call]
            token=None,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=_SCOPES,
        )

        try:
            await asyncio.to_thread(creds.refresh, Request())
        except RefreshError:
            # 401 from Google — refresh_token revoked; user must re-connect
            await self._repo.delete_by_user_id(user_id)
            return None
        except Exception as exc:
            raise GoogleApiError(f"Token refresh failed: {exc}") from exc

        if not creds.token or not creds.expiry:
            return None

        await self._repo.update_tokens(
            user_id=user_id,
            encrypted_access_token=encrypt_token(creds.token),
            token_expires_at=_ensure_utc(creds.expiry),
        )

        return creds.token  # type: ignore[no-any-return]

    async def revoke_access(self, user_id: int) -> None:
        """Delete stored credentials — user must re-authorise to use the bot."""
        await self._repo.delete_by_user_id(user_id)
