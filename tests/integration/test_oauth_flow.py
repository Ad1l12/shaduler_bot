"""Integration tests: Google OAuth callback flow.

The OAuth token exchange (flow.fetch_token) is mocked — no real Google
request is made.  We verify that:
  - tokens are stored encrypted in the DB
  - stored bytes are not the plaintext token (i.e. encryption is applied)
  - the /auth/google/callback endpoint returns the correct HTML
  - an invalid state (non-integer) returns an error page
  - a missing refresh_token (user denied offline access) returns an error page
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.oauth_credential_repo import OAuthCredentialRepository
from src.db.repositories.user_repo import UserRepository
from src.security.encryption import decrypt_token


def _make_mock_credentials(
    token: str = "ya29.access-token",
    refresh_token: str = "1//refresh-token",
    expiry: datetime | None = None,
) -> MagicMock:
    """Return a mock google.oauth2.credentials.Credentials object."""
    creds = MagicMock()
    creds.token = token
    creds.refresh_token = refresh_token
    creds.expiry = expiry or (datetime.now(UTC) + timedelta(hours=1))
    return creds


def _make_mock_flow(creds: MagicMock) -> MagicMock:
    flow = MagicMock()
    flow.fetch_token = MagicMock()
    flow.credentials = creds
    return flow


@pytest.mark.asyncio
async def test_oauth_callback_stores_encrypted_tokens(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /auth/google/callback → tokens persisted encrypted."""
    user_repo = UserRepository(db_session)
    user = await user_repo.create(telegram_id=99887766)
    await db_session.commit()

    creds = _make_mock_credentials()
    flow = _make_mock_flow(creds)

    with (
        patch("src.services.auth_service._make_flow", return_value=flow),
        patch("src.services.auth_service.asyncio.to_thread", new=AsyncMock()),
    ):
        resp = await http_client.get(
            "/auth/google/callback",
            params={"code": "4/auth-code", "state": str(user.id)},
        )

    assert resp.status_code == 200
    assert "подключён" in resp.text

    cred_repo = OAuthCredentialRepository(db_session)
    cred = await cred_repo.get_by_user_id(user.id)
    assert cred is not None

    # Tokens must be stored encrypted (bytes, not plaintext)
    assert cred.encrypted_access_token != b"ya29.access-token"
    assert cred.encrypted_refresh_token != b"1//refresh-token"

    # Decryption must recover the original plaintext
    assert decrypt_token(cred.encrypted_access_token) == "ya29.access-token"
    assert decrypt_token(cred.encrypted_refresh_token) == "1//refresh-token"


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state_returns_error(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A non-integer state → 400 error page, no DB rows created."""
    resp = await http_client.get(
        "/auth/google/callback",
        params={"code": "4/auth-code", "state": "not-an-integer"},
    )

    assert resp.status_code == 400
    assert "подключить" in resp.text.lower() or "ошибка" in resp.text.lower()

    # No credentials should have been written
    from sqlalchemy import func, select

    from src.models.oauth_credential import OAuthCredential
    count = (
        await db_session.execute(select(func.count()).select_from(OAuthCredential))
    ).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_oauth_callback_no_refresh_token_returns_error(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Google returns no refresh_token (user denied offline access) → 400."""
    user_repo = UserRepository(db_session)
    user = await user_repo.create(telegram_id=55443322)
    await db_session.commit()

    # refresh_token=None simulates user denying offline access
    creds = _make_mock_credentials(refresh_token="")
    creds.refresh_token = None  # type: ignore[assignment]
    flow = _make_mock_flow(creds)

    with (
        patch("src.services.auth_service._make_flow", return_value=flow),
        patch("src.services.auth_service.asyncio.to_thread", new=AsyncMock()),
    ):
        resp = await http_client.get(
            "/auth/google/callback",
            params={"code": "4/auth-code", "state": str(user.id)},
        )

    assert resp.status_code == 400

    cred_repo = OAuthCredentialRepository(db_session)
    cred = await cred_repo.get_by_user_id(user.id)
    assert cred is None


@pytest.mark.asyncio
async def test_oauth_callback_google_api_error_returns_502(
    http_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Network failure during token exchange → 502 error page."""
    from src.exceptions import GoogleApiError

    user_repo = UserRepository(db_session)
    user = await user_repo.create(telegram_id=11223344)
    await db_session.commit()

    flow = _make_mock_flow(_make_mock_credentials())

    with (
        patch("src.services.auth_service._make_flow", return_value=flow),
        patch(
            "src.services.auth_service.asyncio.to_thread",
            new=AsyncMock(side_effect=GoogleApiError("network error")),
        ),
    ):
        resp = await http_client.get(
            "/auth/google/callback",
            params={"code": "4/broken-code", "state": str(user.id)},
        )

    assert resp.status_code == 502
