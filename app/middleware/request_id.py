"""Middleware request_id: трасування запиту від входу до access-рядка логу.

1. Бере `X-Request-ID` із заголовка; якщо його немає або він підозрілий — генерує UUID.
2. Кладе його в contextvar — звідти його бачать логер і обробники помилок.
3. Необроблений виняток → лог із traceback + 500 `INTERNAL_ERROR` у єдиному форматі.
4. Додає `X-Request-ID` у відповідь і пише access-рядок: метод, шлях, статус, тривалість.
5. Скидає contextvar.

Чому 500 ловимо тут: стандартний catch-all Starlette працює в зовнішньому
`ServerErrorMiddleware`, де contextvar уже скинуто, — у лозі й відповіді не було б request_id.
"""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.error_handlers import error_response
from app.core.logger import get_logger, request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"
# Дозволяємо лише безпечні символи й розумну довжину: значення потрапляє в логи
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = get_logger("app.middleware")


def resolve_request_id(header_value: str | None) -> str:
    if header_value and VALID_REQUEST_ID.match(header_value):
        return header_value
    return str(uuid.uuid4())


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = request_id_ctx.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = error_response(500, "INTERNAL_ERROR", "Internal server error")

        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = (time.perf_counter() - started) * 1000
        path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        logger.info("%s %s %d %.1fms", request.method, path, response.status_code, duration_ms)
        return response
    finally:
        request_id_ctx.reset(token)
