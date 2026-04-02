import re
from datetime import datetime
from zoneinfo import ZoneInfo

import dateparser
import dateparser.search
from pydantic import ValidationError

from src.schemas.parsed_message import ParsedEvent

_MAX_TEXT_LEN = 512

# "в 18" / "в 9" → "в 18:00" / "в 9:00"  (only bare hours, not already "10:30")
_BARE_HOUR_RE = re.compile(r'\bв\s+([01]?\d|2[0-3])\b(?![:0-9])')

# Russian vague time-of-day words → canonical hour strings
_TIME_OF_DAY: dict[str, str] = {
    "утром": "в 9:00",
    "днём": "в 14:00",
    "вечером": "в 19:00",
    "ночью": "в 0:00",
}


def _normalize(text: str) -> str:
    """Expand bare hours and vague time-of-day words for dateparser."""
    for word, replacement in _TIME_OF_DAY.items():
        text = text.replace(word, replacement)
    return _BARE_HOUR_RE.sub(r'в \1:00', text)


def parse_message(text: str, timezone: str, now: datetime) -> ParsedEvent | None:
    """Parse a free-form Russian text message into a ParsedEvent.

    Returns None if:
    - text is empty or whitespace-only
    - text exceeds 512 characters
    - no date/time expression is found
    - parsed date is not in the future relative to *now*
    - no title remains after removing the date fragments
    """
    if not text or not text.strip():
        return None

    if len(text) > _MAX_TEXT_LEN:
        return None

    # dateparser's RELATIVE_BASE must be naive
    relative_base = now.replace(tzinfo=None) if now.tzinfo else now

    settings: dict[str, object] = {
        "PREFER_DATES_FROM": "future",
        "DATE_ORDER": "DMY",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "TIMEZONE": timezone,
        "RELATIVE_BASE": relative_base,
    }

    normalized = _normalize(text)

    # search_dates finds individual date/time fragments within the text
    results = dateparser.search.search_dates(normalized, languages=["ru"], settings=settings)

    if not results:
        return None

    # Combine all detected date fragments and re-parse them together so that
    # "завтра" + "в 18:00" → tomorrow at 18:00 instead of tomorrow at 12:00
    combined_date_str = " ".join(date_str for date_str, _ in results)
    parsed_dt = dateparser.parse(combined_date_str, languages=["ru"], settings=settings)

    if parsed_dt is None:
        # Fall back to the first fragment's datetime
        parsed_dt = results[0][1]

    # Normalise *now* to timezone-aware for comparison
    now_aware = now.replace(tzinfo=ZoneInfo(timezone)) if now.tzinfo is None else now

    if parsed_dt <= now_aware:
        return None

    # Strip all matched date fragments from the normalised text to get the title
    title_text = normalized
    for date_str, _ in results:
        title_text = title_text.replace(date_str, " ")

    title = " ".join(title_text.split()).strip()

    if not title:
        return None

    # Silently truncate to fit the schema's 200-char limit
    title = title[:200]

    try:
        return ParsedEvent(title=title, start_at=parsed_dt)
    except ValidationError:
        return None
