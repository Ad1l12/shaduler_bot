"""Scheduled task: proactively refresh access tokens expiring within 5 minutes.

Runs every 30 minutes.  Finds all OAuth credentials whose access token expires
within the next 300 seconds and calls AuthService.get_valid_token(), which
internally refreshes and persists the new token.

If the refresh_token has been revoked, AuthService deletes the credential row
(the user will see a prompt to /connect again).  Any other error is logged and
skipped so one bad credential does not block the rest.

Each credential is refreshed in its own session + transaction.
"""

import structlog

from src.db.repositories.oauth_credential_repo import OAuthCredentialRepository
from src.db.session import AsyncSessionFactory
from src.services.auth_service import AuthService

logger = structlog.get_logger(__name__)

_REFRESH_WINDOW_SECONDS = 300  # refresh tokens expiring within 5 minutes


async def refresh_expiring_tokens() -> None:
    """Entry point called by APScheduler every 30 minutes."""
    async with AsyncSessionFactory() as session:
        repo = OAuthCredentialRepository(session)
        expiring = await repo.get_expiring_soon(within_seconds=_REFRESH_WINDOW_SECONDS)

    if not expiring:
        return

    logger.info("token_refresh_start", count=len(expiring))

    for cred in expiring:
        async with AsyncSessionFactory() as session:
            try:
                auth_service = AuthService(session)
                token = await auth_service.get_valid_token(cred.user_id)
                await session.commit()
                if token:
                    logger.info("token_refreshed", user_id=cred.user_id)
                else:
                    logger.info("token_refresh_revoked", user_id=cred.user_id)
            except Exception as exc:
                await session.rollback()
                logger.warning(
                    "token_refresh_failed",
                    user_id=cred.user_id,
                    error=str(exc),
                )
