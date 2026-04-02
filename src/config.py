from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_log_level: LogLevel = LogLevel.DEBUG
    app_base_url: str = "http://localhost:8000"

    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = Field(default="")

    # Database
    database_url: str = "postgresql+asyncpg://bot:localpass@localhost:5432/calendar_bot"

    # Encryption
    encryption_key: str

    # Sentry (optional)
    sentry_dsn: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.google_redirect_uri:
            self.google_redirect_uri = f"{self.app_base_url}/auth/google/callback"


settings = Settings()  # type: ignore[call-arg,unused-ignore]
