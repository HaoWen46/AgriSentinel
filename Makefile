# AgriSentinel — one-command targets. Pipeline stages run inside the `api`
# container (which has all deps + network); `test`/`lint` run on the host via uv.
.DEFAULT_GOAL := help
DC   := docker compose
EXEC := docker compose exec -T api agrisentinel

.PHONY: help up down logs ps init ingest seed detect tile join evaluate dossiers \
        pipeline demo demo-offline serve test lint clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Build images and bring the whole stack up (waits for health)
	$(DC) up -d --build --wait

down: ## Stop the stack
	$(DC) down

logs: ## Tail logs
	$(DC) logs -f

ps: ## Show service status
	$(DC) ps

init: ## Create DB extensions + schema (idempotent)
	$(EXEC) init-db

ingest: ## Phase 1: imagery + labels + parcels + statutes (live, with offline fallback)
	$(EXEC) init-db
	-$(EXEC) ingest-stac
	-$(EXEC) ingest-labels
	$(EXEC) load-parcels
	$(EXEC) fetch-laws

seed: ## Phase 1 (offline): synthetic imagery + sample labels + parcels + statutes
	$(EXEC) init-db
	$(EXEC) seed

detect: ## Phase 2: change detection over the AOI
	$(EXEC) detect

tile: ## Phase 2 (alt): PySpark/single-process tiled detection
	$(EXEC) tile-detect

join: ## Phase 3: spatial join detections x farmland parcels
	$(EXEC) join

evaluate: ## Phase 3: precision/recall vs Disfactory labels
	$(EXEC) evaluate

dossiers: ## Phase 4: generate enforcement dossiers (needs ANTHROPIC_API_KEY)
	$(EXEC) dossiers

pipeline: detect join evaluate dossiers ## Phases 2-4 over the current data

demo: up ingest pipeline ## Full live demo end-to-end → http://localhost:8000
	@echo "\n✓ Demo ready: open http://localhost:8000"

demo-offline: up seed pipeline ## Full offline demo (no network needed) → http://localhost:8000
	@echo "\n✓ Offline demo ready: open http://localhost:8000"

serve: ## Run the API on the host (needs services reachable)
	uv run agrisentinel serve --reload

test: ## Run the test suite (host, via uv)
	uv run --extra dev python -m pytest -q

lint: ## Lint with ruff (host, via uv)
	uv run --extra dev ruff check .

clean: ## Stop stack and remove volumes (destroys local data)
	$(DC) down -v
