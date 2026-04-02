from datetime import datetime

from pydantic import BaseModel, field_validator


class ParsedEvent(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def validate_title_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("title must be at most 200 characters")
        if not v.strip():
            raise ValueError("title cannot be empty")
        return v
