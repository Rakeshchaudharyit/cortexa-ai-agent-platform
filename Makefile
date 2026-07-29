# Cortexa AI Agent Platform — developer commands (Phase 1)

.PHONY: help install dev up down build logs backend-logs frontend-logs \
	test test-backend test-frontend lint format typecheck migrate \
	health ready validate clean compose-config secrets-check

help:
	@echo "Cortexa AI Agent Platform — Phase 3"
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install backend + frontend dependencies locally"
	@echo "  make dev             Run backend (uvicorn) and note frontend npm run dev"
	@echo ""
	@echo "Docker:"
	@echo "  make up              Build and start Compose stack"
	@echo "  make down            Stop Compose stack"
	@echo "  make build           Build Compose images"
	@echo "  make logs            Follow all service logs"
	@echo "  make backend-logs    Follow backend logs"
	@echo "  make frontend-logs   Follow frontend logs"
	@echo ""
	@echo "Quality:"
	@echo "  make test            Run backend + frontend tests"
	@echo "  make test-backend    Run backend pytest"
	@echo "  make test-frontend   Run frontend vitest"
	@echo "  make lint            Run ruff + eslint"
	@echo "  make format          Format backend with ruff"
	@echo "  make typecheck       Run mypy + tsc"
	@echo "  make validate        Full Phase 1–3 validation suite"
	@echo ""
	@echo "Ops:"
	@echo "  make migrate         Run Alembic upgrade head (Docker backend)"
	@echo "  make health          curl GET /health"
	@echo "  make ready           curl GET /ready"
	@echo "  make clean           Remove caches and local build artifacts"
	@echo "  make compose-config  Validate docker compose config"
	@echo "  make secrets-check   Heuristic scan for private key blocks"

install:
	cd backend && python3 -m pip install -e ".[dev]"
	cd frontend && npm install

dev:
	@echo "Starting backend on http://$${BACKEND_HOST:-127.0.0.1}:$${BACKEND_PORT:-8000}"
	@echo "In another terminal: cd frontend && npm run dev"
	cd backend && uvicorn app.main:app --host $${BACKEND_HOST:-127.0.0.1} --port $${BACKEND_PORT:-8000} --reload

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

backend-logs:
	docker compose logs -f backend

frontend-logs:
	docker compose logs -f frontend

test: test-backend test-frontend

test-backend:
	@if docker compose ps --status running backend 2>/dev/null | grep -q backend; then \
		docker compose exec -T backend pytest; \
	else \
		cd backend && pytest; \
	fi

test-frontend:
	@if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then \
		docker compose exec -T frontend npm test -- --run; \
	else \
		cd frontend && npm test -- --run; \
	fi

lint:
	@if docker compose ps --status running backend 2>/dev/null | grep -q backend; then \
		docker compose exec -T backend ruff check .; \
	else \
		cd backend && ruff check .; \
	fi
	@if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then \
		docker compose exec -T frontend npm run lint; \
	else \
		cd frontend && npm run lint; \
	fi

format:
	@if docker compose ps --status running backend 2>/dev/null | grep -q backend; then \
		docker compose exec -T backend ruff format .; \
	else \
		cd backend && ruff format .; \
	fi

typecheck:
	@if docker compose ps --status running backend 2>/dev/null | grep -q backend; then \
		docker compose exec -T backend mypy app; \
	else \
		cd backend && mypy app; \
	fi
	@if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then \
		docker compose exec -T frontend npm run typecheck; \
	else \
		cd frontend && npm run typecheck; \
	fi

migrate:
	docker compose exec -T backend alembic upgrade head

health:
	curl -fsS -i http://localhost:$${BACKEND_PORT:-8000}/health

ready:
	curl -fsS -i http://localhost:$${BACKEND_PORT:-8000}/ready

compose-config:
	docker compose config >/dev/null
	@echo "docker compose config: OK"

secrets-check:
	@if command -v rg >/dev/null 2>&1; then \
		if rg -n --hidden -g '!.git/**' -g '!.env.example' \
			-e 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY' \
			-e 'AKIA[0-9A-Z]{16}' \
			. ; then \
			echo "secrets-check: FAILED — possible secret material detected"; \
			exit 1; \
		fi; \
	else \
		if grep -R -n -E 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}' \
			--exclude-dir=.git --exclude=.env.example . ; then \
			echo "secrets-check: FAILED — possible secret material detected"; \
			exit 1; \
		fi; \
	fi
	@echo "secrets-check: OK"

validate: compose-config secrets-check
	@./scripts/validate-phase1.sh

clean:
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/**/__pycache__
	# Host-side full tree only. Inside Docker, stop frontend before wiping the
	# named volume .next (never delete selected files under .next/cache live).
	rm -rf frontend/.next frontend/coverage frontend/node_modules/.cache
	find backend -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: OK"
