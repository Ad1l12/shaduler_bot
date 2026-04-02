from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_session
from src.exceptions import GoogleApiError
from src.services.auth_service import AuthService

router = APIRouter()

_SUCCESS_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<title>Подключено</title></head><body>
<h2>✅ Google Calendar подключён!</h2>
<p>Можно закрыть эту вкладку и вернуться в Telegram.</p>
</body></html>
"""

_ERROR_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<title>Ошибка</title></head><body>
<h2>❌ Не удалось подключить Google Calendar</h2>
<p>Попробуйте снова через команду <b>/connect</b> в Telegram.</p>
</body></html>
"""


@router.get("/auth/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Handle Google OAuth redirect and persist the user's tokens."""
    try:
        service = AuthService(session)
        success = await service.handle_callback(code, state)
    except GoogleApiError:
        return HTMLResponse(content=_ERROR_HTML, status_code=502)

    if success:
        return HTMLResponse(content=_SUCCESS_HTML, status_code=200)
    return HTMLResponse(content=_ERROR_HTML, status_code=400)
