"""Unit tests for parse_message — Stage 4: Parser Service.

Fixed reference point: 2026-04-02 12:00:00 UTC (Thursday).
- "tomorrow"           → 2026-04-03 (Friday)
- "day after tomorrow" → 2026-04-04 (Saturday)
- "next Friday"        → 2026-04-03 (tomorrow is Friday)
- Past date            → 2026-01-01 (clearly in the past)
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.schemas.parsed_message import ParsedEvent
from src.services.parser_service import parse_message

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 4, 2, 12, 0, 0, tzinfo=timezone.utc)  # Thursday 12:00 UTC
TZ = "UTC"


def _parse(text: str) -> ParsedEvent | None:
    return parse_message(text, TZ, NOW)


# ---------------------------------------------------------------------------
# 1. "завтра в 18 тренировка"
# ---------------------------------------------------------------------------

def test_tomorrow_18_training() -> None:
    result = _parse("завтра в 18 тренировка")
    assert result is not None
    assert "тренировка" in result.title
    assert result.start_at.day == 3        # April 3
    assert result.start_at.hour == 18      # 18:00 after bare-hour normalisation
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 2. "в пятницу в 20 ужин с друзьями"
# ---------------------------------------------------------------------------

def test_friday_20_dinner() -> None:
    result = _parse("в пятницу в 20 ужин с друзьями")
    assert result is not None
    assert "ужин" in result.title
    assert result.start_at.weekday() == 4  # Friday
    assert result.start_at.hour == 20      # 20:00 after bare-hour normalisation
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 3. "послезавтра стоматолог"
# ---------------------------------------------------------------------------

def test_day_after_tomorrow_dentist() -> None:
    result = _parse("послезавтра стоматолог")
    assert result is not None
    assert "стоматолог" in result.title
    assert result.start_at.day == 4        # April 4
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 4. "через 2 часа созвон"
# ---------------------------------------------------------------------------

def test_in_2_hours_call() -> None:
    result = _parse("через 2 часа созвон")
    assert result is not None
    assert "созвон" in result.title
    assert result.start_at.hour == 14      # 12:00 + 2h
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 5. "15 мая в 10:30 собеседование"
# ---------------------------------------------------------------------------

def test_may_15_interview() -> None:
    result = _parse("15 мая в 10:30 собеседование")
    assert result is not None
    assert "собеседование" in result.title
    assert result.start_at.month == 5
    assert result.start_at.day == 15
    assert result.start_at.hour == 10
    assert result.start_at.minute == 30


# ---------------------------------------------------------------------------
# 6. "сегодня вечером йога"
# ---------------------------------------------------------------------------

def test_today_evening_yoga() -> None:
    # "вечером" normalised to "в 19:00"; today at 19:00 > NOW (12:00)
    result = _parse("сегодня вечером йога")
    assert result is not None
    assert "йога" in result.title
    assert result.start_at.hour == 19      # "вечером" → 19:00
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 7. Empty string → None
# ---------------------------------------------------------------------------

def test_empty_string_returns_none() -> None:
    assert _parse("") is None


# ---------------------------------------------------------------------------
# 8. Whitespace-only string → None
# ---------------------------------------------------------------------------

def test_whitespace_only_returns_none() -> None:
    assert _parse("   \t\n  ") is None


# ---------------------------------------------------------------------------
# 9. "привет" — no date → None
# ---------------------------------------------------------------------------

def test_no_date_returns_none() -> None:
    assert _parse("привет") is None


# ---------------------------------------------------------------------------
# 10. Arbitrary text without any date → None
# ---------------------------------------------------------------------------

def test_nonsense_text_returns_none() -> None:
    assert _parse("абракадабра фуфу блабла") is None


# ---------------------------------------------------------------------------
# 11. Very long text (>512 chars) → None
# ---------------------------------------------------------------------------

def test_too_long_text_returns_none() -> None:
    long_text = "завтра в 18 тренировка " + "а" * 500
    assert len(long_text) > 512
    assert _parse(long_text) is None


# ---------------------------------------------------------------------------
# 12. Date in the past → None
# ---------------------------------------------------------------------------

def test_past_date_returns_none() -> None:
    assert _parse("1 января 2020 в 10:00 встреча") is None


# ---------------------------------------------------------------------------
# 13. Successful parse returns a ParsedEvent instance
# ---------------------------------------------------------------------------

def test_returns_parsed_event_instance() -> None:
    result = _parse("завтра в 15 встреча с командой")
    assert isinstance(result, ParsedEvent)


# ---------------------------------------------------------------------------
# 14. start_at is timezone-aware
# ---------------------------------------------------------------------------

def test_start_at_is_timezone_aware() -> None:
    result = _parse("завтра в 9 созвон")
    assert result is not None
    assert result.start_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 15. Title longer than 200 chars is silently truncated to 200
# ---------------------------------------------------------------------------

def test_long_title_truncated_to_200() -> None:
    long_title = "а" * 250
    text = f"завтра в 18 {long_title}"
    assert len(text) <= 512
    result = _parse(text)
    assert result is not None
    assert len(result.title) <= 200


# ---------------------------------------------------------------------------
# 16. "через час митинг"
# ---------------------------------------------------------------------------

def test_in_1_hour_meeting() -> None:
    result = _parse("через час митинг")
    assert result is not None
    assert "митинг" in result.title
    assert result.start_at.hour == 13      # 12:00 + 1h
    assert result.start_at > NOW


# ---------------------------------------------------------------------------
# 17. end_at defaults to None
# ---------------------------------------------------------------------------

def test_end_at_is_none_by_default() -> None:
    result = _parse("завтра в 10 завтрак")
    assert result is not None
    assert result.end_at is None


# ---------------------------------------------------------------------------
# 18. ParsedEvent schema rejects title longer than 200 chars
# ---------------------------------------------------------------------------

def test_parsed_event_schema_rejects_long_title() -> None:
    with pytest.raises(ValidationError):
        ParsedEvent(title="х" * 201, start_at=NOW)


# ---------------------------------------------------------------------------
# 19. ParsedEvent schema rejects empty title
# ---------------------------------------------------------------------------

def test_parsed_event_schema_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        ParsedEvent(title="", start_at=NOW)


# ---------------------------------------------------------------------------
# 20. "через 30 минут обед"
# ---------------------------------------------------------------------------

def test_in_30_minutes_lunch() -> None:
    result = _parse("через 30 минут обед")
    assert result is not None
    assert "обед" in result.title
    assert result.start_at > NOW
