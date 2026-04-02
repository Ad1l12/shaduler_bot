from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.session import AsyncSessionFactory

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, object]:
    from src.main import get_uptime

    db_ok = await _check_db()
    status = "ok" if db_ok else "degraded"

    return {
        "status": status,
        "uptime_seconds": round(get_uptime(), 1),
        "db": "ok" if db_ok else "error",
    }


async def _check_db() -> bool:
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
