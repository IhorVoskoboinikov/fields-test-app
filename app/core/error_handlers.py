"""Перетворення винятків на HTTP-відповіді в єдиному форматі `{"error": {...}}`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logger import get_logger, request_id_ctx
from app.schemas.common import ErrorBody, ErrorResponse

logger = get_logger(__name__)

HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Будує JSON-відповідь помилки з request_id поточного запиту.

    `details` є у відповіді лише тоді, коли деталі є (`exclude_none`).
    """
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details, request_id=request_id_ctx.get()
        )
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Доменні винятки: статус і код беруться з самого винятку. 4xx — WARNING, 5xx — ERROR."""
    level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    logger.log(level, "%s %s: %s %s", exc.status_code, exc.code, exc.message, exc.details or "")
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Помилки валідації запиту → 422; `input` і `ctx` вирізаємо (можуть бути великими)."""
    details = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    logger.warning("422 VALIDATION_ERROR: %s", details)
    return error_response(422, "VALIDATION_ERROR", "Request validation failed", details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTP-винятки Starlette (немає роуту, метод не дозволено тощо) у тому самому форматі."""
    code = HTTP_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    logger.warning("%s %s: %s", exc.status_code, code, exc.detail)
    return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    """Реєструє всі обробники. Необроблені винятки (500) ловить middleware request_id."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
