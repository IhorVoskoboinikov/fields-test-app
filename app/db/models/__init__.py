"""ORM-моделі. Імпорт тут реєструє їх у `Base.metadata` (потрібно для Alembic)."""

from app.db.models.field import Field

__all__ = ["Field"]
