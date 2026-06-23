# =============================================================================
# VisionTrack — common dev commands
# =============================================================================

.PHONY: help up down logs ps build rebuild reset migrate revision shell-backend shell-db test lint

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

up:  ## Start the full stack
	docker compose up -d
	@echo ""
	@echo "  Frontend:  http://localhost:5173"
	@echo "  Backend:   http://localhost:8000/docs"
	@echo "  MinIO:     http://localhost:9001"
	@echo ""
	@echo "  Login:     admin@visiontrack.io / ChangeMe123!"

down:  ## Stop the stack (keeps volumes)
	docker compose down

logs:  ## Tail logs from all services
	docker compose logs -f --tail=100

ps:  ## Show running services
	docker compose ps

build:  ## Rebuild backend and frontend images
	docker compose build backend frontend

rebuild: down build up  ## Stop, rebuild, restart

reset:  ## DANGER: stop and wipe all data (volumes deleted)
	docker compose down -v
	@echo "All volumes wiped. Run 'make up' to start fresh."

migrate:  ## Run database migrations
	docker compose exec backend alembic upgrade head

revision:  ## Create a new auto-generated migration (use: make revision m="add cameras")
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

shell-backend:  ## Open a shell inside the backend container
	docker compose exec backend bash

shell-db:  ## Open a psql shell against the database
	docker compose exec postgres psql -U visiontrack -d visiontrack

test:  ## Run backend tests
	docker compose exec backend pytest -v

lint:  ## Lint the backend
	docker compose exec backend ruff check .
