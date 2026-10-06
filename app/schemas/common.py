"""Спільні схеми: єдиний формат помилки та відповідь /health."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Тіло помилки: машинний код, повідомлення, деталі та request_id для пошуку в логах."""

    code: str = Field(examples=["FIELD_NOT_FOUND"])
    message: str = Field(examples=["Field not found"])
    details: Any = None
    request_id: str = Field(examples=["3f2a9c1e-7d4b-4c1a-9a0e-2b5f6c7d8e9f"])


class ErrorResponse(BaseModel):
    """Єдиний формат усіх помилок API: `{"error": {...}}`."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """Відповідь /health, коли застосунок і база доступні."""

    status: Literal["ok"] = "ok"
