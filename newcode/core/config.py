"""Global application configuration via pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # LLM Settings
    OPENAI_API_BASE: str = Field(
        default="https://1yuanapi.com/v1",
        description="Base URL for OpenAI-compatible API endpoint",
    )
    OPENAI_API_KEY: str = Field(
        default="",
        description="API key for LLM services",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-5.6-terra",
        description="Default model name for chat and completions",
    )

    # Database Settings
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///suredesk.db",
        description="SQLAlchemy async database connection string",
    )

    # Application Settings
    APP_NAME: str = Field(
        default="SureDesk",
        description="Application name",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="Application version",
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode flag",
    )
    ENVIRONMENT: str = Field(
        default="development",
        description="Runtime environment (development, test, production)",
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()


settings: Settings = get_settings()

