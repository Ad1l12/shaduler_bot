from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OAuthCredential(Base):
    __tablename__ = "oauth_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(
        Enum("google", name="oauth_provider_enum"), nullable=False
    )
    encrypted_refresh_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_access_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calendar_id: Mapped[str] = mapped_column(String(256), server_default="primary", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
