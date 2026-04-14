.DEFAULT_GOAL := help

COMPOSE := docker compose -f infra/docker/dev.yml

.PHONY: help install dev test lint build codegen up down clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Voyagent — available targets:\n\n"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install JS + Python deps
	pnpm install && uv sync

dev: ## Run all dev servers (turbo)
	pnpm dev

test: ## Run JS + Python tests
	pnpm test && uv run pytest

lint: ## Lint JS + Python
	pnpm lint && uv run ruff check .

build: ## Build all JS packages/apps
	pnpm build

codegen: ## Regenerate TS types from Pydantic canonical models
	pnpm codegen

up: ## Start local dev infra (pg, redis, temporal, minio)
	$(COMPOSE) up -d

down: ## Stop local dev infra
	$(COMPOSE) down

clean: ## Remove build outputs and caches
	rm -rf node_modules .turbo dist .next **/dist **/.next **/.turbo **/__pycache__ .venv
