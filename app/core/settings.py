"""Налаштування застосунку: усе читається зі змінних оточення або файлу `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфігурація застосунку.

    Значення беруться зі змінних оточення; локально — ще й з `.env`.
    У docker compose всі значення задані прямо в `docker-compose.yml`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://fields:fields@localhost:5433/fields"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Повертає єдиний екземпляр налаштувань (створюється при першому виклику)."""
    return Settings()
