from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Конфігурація застосунку.

    Джерело — змінні оточення, локально ще й файл `.env` (шаблон — `.env.example`).
    Значення за замовчуванням збігаються з `.env.example`, тож без `.env` усе теж працює.
    У docker compose ті самі змінні передаються контейнерам, але хост і порт бази —
    `db:5432` (адреса всередині мережі compose).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_user: str = "fields"
    postgres_password: str = "fields"
    postgres_db: str = "fields"
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    log_level: str = "INFO"

    @property
    def database_url(self) -> str:
        """URL для SQLAlchemy з окремих змінних; пароль екранується коректно."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
