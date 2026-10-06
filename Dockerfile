# syntax=docker/dockerfile:1

# --- збірка: залежності через uv окремим шаром до коду ---
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Шар залежностей: перезбирається лише при зміні pyproject.toml / uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- фінальний образ: без uv і кешу, процес від непривілейованого користувача ---
FROM python:3.12-slim
RUN useradd --create-home app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
