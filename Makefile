.DEFAULT_GOAL := help
.PHONY: help install lint format test up down reset logs db migrate revision

help:  ## Список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install:  ## Встановити залежності (uv sync)
	uv sync

lint:  ## Перевірити код (ruff)
	uv run ruff check . && uv run ruff format --check .

format:  ## Відформатувати код (ruff)
	uv run ruff check --fix . && uv run ruff format .

test:  ## Запустити тести (потрібен Docker)
	uv run pytest

up:  ## Підняти всі сервіси
	docker compose up -d --build

down:  ## Зупинити сервіси
	docker compose down

reset:  ## Зупинити сервіси й видалити дані БД
	docker compose down -v

logs:  ## Логи API
	docker compose logs -f api

db:  ## Підняти лише базу (і pgAdmin) для локальної розробки
	docker compose up -d db pgadmin

migrate:  ## Застосувати міграції локально
	uv run alembic upgrade head

revision:  ## Згенерувати міграцію: make revision m="опис"
	uv run alembic revision --autogenerate -m "$(m)"
