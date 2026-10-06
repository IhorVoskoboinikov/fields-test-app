.DEFAULT_GOAL := help
.PHONY: help install lint format test

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
