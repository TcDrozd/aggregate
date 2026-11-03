UV ?= uv
RUN := $(UV) run

.DEFAULT_GOAL := help
.PHONY: help setup check lint fmt typecheck test migrate migration-check run

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install dependencies and the pre-commit hooks
	$(UV) sync
	$(RUN) pre-commit install

check: lint typecheck test migration-check ## Everything CI's Python jobs run; run before every commit

lint: ## ruff lint and format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt: ## Format and apply safe lint fixes
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck: ## mypy --strict on src/
	$(RUN) mypy

test: ## pytest with coverage; fails under 85%
	$(RUN) pytest --cov --cov-report=term-missing

migrate: ## Apply migrations to AGGREGATE_DATABASE_URL
	$(RUN) aggregate db upgrade

migration-check: ## Migrate an empty database to head, then fail if models drift from migrations
	@tmp=$$(mktemp -d) && trap 'rm -rf "$$tmp"' EXIT && \
	export AGGREGATE_DATABASE_URL="sqlite:///$$tmp/check.db" && \
	$(RUN) alembic upgrade head && \
	$(RUN) alembic check

run: ## Serve the API locally with auto-reload
	$(RUN) uvicorn aggregate.main:create_app --factory --reload
