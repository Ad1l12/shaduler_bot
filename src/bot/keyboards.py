"""Inline keyboard factories and CallbackData schemas."""

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ConfirmEventCallback(CallbackData, prefix="ce"):
    event_id: int


class CancelEventCallback(CallbackData, prefix="xe"):
    event_id: int


def confirm_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Return a two-button keyboard: ✅ Создать / ❌ Отмена."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Создать",
        callback_data=ConfirmEventCallback(event_id=event_id),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=CancelEventCallback(event_id=event_id),
    )
    return builder.as_markup()
