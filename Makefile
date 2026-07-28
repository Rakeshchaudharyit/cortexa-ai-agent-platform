# Cortexa AI Agent Platform — developer convenience targets
# Phase 0: validation and inspection only.

.PHONY: help tree validate compose-config python-syntax git-status secrets-check phase0

help:
	@echo "Cortexa AI Agent Platform"
	@echo ""
	@echo "Phase 0 targets:"
	@echo "  make tree            Print repository tree"
	@echo "  make compose-config  Validate docker-compose.yml"
	@echo "  make python-syntax   Parse Python files under backend/"
	@echo "  make git-status      Show git status"
	@echo "  make secrets-check   Heuristic scan for private key blocks"
	@echo "  make validate        Run Phase 0 validation suite"
	@echo "  make phase0          Alias for validate"

tree:
	@if command -v tree >/dev/null 2>&1; then \
		tree -a -I '.git|__pycache__|node_modules|.next'; \
	else \
		find . -path ./.git -prune -o -print | sed 's|[^/]*/|  |g'; \
	fi

compose-config:
	docker compose config >/dev/null
	@echo "docker compose config: OK"

python-syntax:
	@python3 scripts/check-python-syntax.py

git-status:
	git status

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
	@echo "secrets-check: OK (no private-key / AKIA patterns found)"

validate:
	@./scripts/validate-phase0.sh

phase0: validate
