from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Тіло помилки: машинний код, повідомлення і деталі (request_id — у `X-Request-ID`)."""

    code: str = Field(examples=["FIELD_NOT_FOUND"])
    message: str = Field(examples=["Field not found"])
    details: Any = Field(None, description="Деталі помилки; поля немає, якщо деталей немає")


class ErrorResponse(BaseModel):
    """Єдиний формат усіх помилок API: `{"error": {...}}`."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """Відповідь /health, коли застосунок і база доступні."""

    status: Literal["ok"] = "ok"
