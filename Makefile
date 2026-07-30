# Cortexa AI Agent Platform — developer commands (Phase 5)

.PHONY: help install dev up down build logs backend-logs frontend-logs \
	test test-backend test-frontend lint format typecheck migrate \
	health ready validate clean compose-config compose-identity auth-hostname \
	secrets-check reset-dev-database \
	test-services-up test-db-migrate test-services-down test-services-reset \
	validate-preserve-before validate-preserve-after validate-preserve-compare

COMPOSE_TEST := COMPOSE_IGNORE_ORPHANS=1 docker compose -p cortexa-test -f docker-compose.test.yml

help:
	@echo "Cortexa AI Agent Platform — Phase 5"
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install backend + frontend dependencies locally"
	@echo "  make dev             Run backend (uvicorn) and note frontend npm run dev"
	@echo ""
	@echo "Docker:"
	@echo "  make up              Build and start Compose stack"
	@echo "  make down            Stop Compose stack (preserves volumes)"
	@echo "  make build           Build Compose images"
	@echo "  make logs            Follow all service logs"
	@echo "  make backend-logs    Follow backend logs"
	@echo "  make frontend-logs   Follow frontend logs"
	@echo "  make compose-identity  Verify Compose project/volume/db identity"
	@echo "  make auth-hostname     Verify browser/API auth hosts are not mixed"
	@echo "  make reset-dev-database  DESTRUCTIVE reset (typed confirmation)"
	@echo ""
	@echo "Isolated tests (never touches cortexa_agent):"
	@echo "  make test-services-up     Start postgres-test + redis-test"
	@echo "  make test-db-migrate      Migrate cortexa_agent_test + set test identity"
	@echo "  make test-backend         Run pytest against cortexa_agent_test"
	@echo "  make test-services-down   Stop test stack (keeps test volume)"
	@echo "  make test-services-reset  Stop test stack and remove TEST volumes only"
	@echo ""
	@echo "Quality:"
	@echo "  make test            Run backend + frontend tests (isolated DB)"
	@echo "  make test-frontend   Run frontend vitest"
	@echo "  make lint            Run ruff + eslint"
	@echo "  make format          Format backend with ruff"
	@echo "  make typecheck       Run mypy + tsc"
	@echo "  make validate        Full validation (preserves development data)"
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

# Volumes are preserved. Never add -v here.
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

test-services-up:
	@docker network create cortexa-test-net >/dev/null 2>&1 || true
	@docker volume create cortexa_postgres_test_data >/dev/null 2>&1 || true
	$(COMPOSE_TEST) up -d postgres-test redis-test
	@echo "test-services-up: waiting for healthy postgres-test/redis-test"
	@for _ in $$(seq 1 60); do \
		if $(COMPOSE_TEST) exec -T postgres-test pg_isready -U cortexa -d cortexa_agent_test >/dev/null 2>&1 \
			&& $(COMPOSE_TEST) exec -T redis-test redis-cli ping 2>/dev/null | grep -q PONG; then \
			echo "test-services-up: OK"; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "test-services-up: FAILED — services not healthy" >&2; \
	exit 1

test-db-migrate:
	@./scripts/migrate_test_database.sh

# Backend pytest ALWAYS uses the isolated test Compose project.
# Never: docker compose exec backend pytest (that wiped cortexa_agent).
test-backend: test-services-up test-db-migrate
	$(COMPOSE_TEST) run --rm backend-test "pytest"

test-services-down:
	# Stops test containers only. Keeps cortexa_postgres_test_data.
	# Never touches development cortexa_postgres_data.
	$(COMPOSE_TEST) down
	@echo "test-services-down: OK (test volume retained)"

test-services-reset:
	# Removes ONLY explicitly named test volumes. Never development volumes.
	$(COMPOSE_TEST) down
	@docker volume rm cortexa_postgres_test_data 2>/dev/null || true
	@echo "test-services-reset: OK (removed cortexa_postgres_test_data only)"

test: test-backend test-frontend

test-frontend:
	@if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then \
		docker compose exec -T -u cortexa frontend npm test -- --run; \
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
	@$(COMPOSE_TEST) config >/dev/null
	@echo "docker compose config: OK (dev + test)"

compose-identity:
	@./scripts/check_compose_identity.sh

auth-hostname:
	@./scripts/check_auth_hostname.sh

# Destructive — not part of normal workflows. Requires typed confirmation.
reset-dev-database:
	@./scripts/reset_dev_database.sh

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

validate-preserve-before:
	@./scripts/verify_validation_preserves_dev_data.sh before

validate-preserve-after:
	@./scripts/verify_validation_preserves_dev_data.sh after

validate-preserve-compare:
	@./scripts/verify_validation_preserves_dev_data.sh compare

validate: compose-config compose-identity auth-hostname secrets-check validate-preserve-before
	@./scripts/validate-phase1.sh
	@$(MAKE) validate-preserve-after
	@$(MAKE) validate-preserve-compare

clean:
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/**/__pycache__
	# Host-side full tree only. Inside Docker, stop frontend before wiping the
	# named volume .next (never delete selected files under .next/cache live).
	rm -rf frontend/.next frontend/coverage frontend/node_modules/.cache
	find backend -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "clean: OK"
