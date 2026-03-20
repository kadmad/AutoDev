.DEFAULT_GOAL := help
SHELL         := /bin/bash
BACKEND_DIR   := backend
FRONTEND_DIR  := frontend
PYTHON        := $(BACKEND_DIR)/venv/bin/python
PIP           := $(BACKEND_DIR)/venv/bin/pip
UVICORN       := $(BACKEND_DIR)/venv/bin/uvicorn
RQ            := $(BACKEND_DIR)/venv/bin/rq

# ── Colours ───────────────────────────────────────────────────────────────────
BOLD  := \033[1m
RESET := \033[0m
GREEN := \033[32m
CYAN  := \033[36m

# ══════════════════════════════════════════════════════════════════════════════
#  HELP
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: help
help:
	@echo ""
	@echo "$(BOLD)AutoDev — available commands$(RESET)"
	@echo ""
	@echo "  $(CYAN)make install$(RESET)        Install all backend + frontend dependencies"
	@echo "  $(CYAN)make dev$(RESET)            Start full stack (infra + backend + worker + frontend)"
	@echo "  $(CYAN)make backend$(RESET)        Start FastAPI backend only  (port 8000)"
	@echo "  $(CYAN)make worker$(RESET)         Start rq pipeline worker only"
	@echo "  $(CYAN)make frontend$(RESET)       Start React frontend only   (port 3000)"
	@echo "  $(CYAN)make infra-up$(RESET)       Start PostgreSQL + Redis via Docker"
	@echo "  $(CYAN)make infra-down$(RESET)     Stop PostgreSQL + Redis"
	@echo "  $(CYAN)make db-reset$(RESET)       Drop and recreate autodev_db"
	@echo "  $(CYAN)make test$(RESET)           Run backend tests"
	@echo "  $(CYAN)make clean$(RESET)          Remove venv, node_modules, caches"
	@echo "  $(CYAN)make env$(RESET)            Copy .env.example → backend/.env (first-time setup)"
	@echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  INSTALL
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: install install-backend install-frontend env

env:
	@if [ ! -f $(BACKEND_DIR)/.env ]; then \
		cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env; \
		echo "$(GREEN)Created $(BACKEND_DIR)/.env — edit it with your credentials$(RESET)"; \
	else \
		echo "$(BACKEND_DIR)/.env already exists, skipping"; \
	fi

install-backend:
	@echo "$(BOLD)[backend] Creating virtualenv…$(RESET)"
	@python3 -m venv $(BACKEND_DIR)/venv
	@echo "$(BOLD)[backend] Installing dependencies…$(RESET)"
	@$(PIP) install --upgrade pip -q
	@$(PIP) install -e "$(BACKEND_DIR)[dev]" -q
	@echo "$(GREEN)[backend] Done$(RESET)"

install-frontend:
	@echo "$(BOLD)[frontend] Installing npm packages…$(RESET)"
	@cd $(FRONTEND_DIR) && npm install
	@echo "$(GREEN)[frontend] Done$(RESET)"

install: env install-backend install-frontend
	@echo ""
	@echo "$(GREEN)$(BOLD)All dependencies installed.$(RESET)"
	@echo "Edit $(BACKEND_DIR)/.env, then run:  make dev"
	@echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: infra-up infra-down

infra-up:
	@echo "$(BOLD)[infra] Starting PostgreSQL + Redis…$(RESET)"
	@docker compose up -d
	@sleep 2

infra-down:
	@docker compose down

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: db-reset

db-reset:
	@echo "$(BOLD)[db] Dropping and recreating autodev_db…$(RESET)"
	@psql postgres -c "DROP DATABASE IF EXISTS autodev_db;"
	@psql postgres -c "CREATE DATABASE autodev_db;"
	@echo "$(GREEN)[db] autodev_db recreated$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  RUN — individual services
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: backend worker frontend

backend:
	@echo "$(BOLD)[backend] Starting FastAPI on :8000…$(RESET)"
	@cd $(BACKEND_DIR) && ../$(UVICORN) app.main:app --port 8000 --reload

worker:
	@echo "$(BOLD)[worker] Starting rq worker…$(RESET)"
	@cd $(BACKEND_DIR) && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
		../$(RQ) worker pipeline:default pipeline:agents --url redis://localhost:6379

frontend:
	@echo "$(BOLD)[frontend] Starting Vite on :3000…$(RESET)"
	@cd $(FRONTEND_DIR) && npm run dev

# ══════════════════════════════════════════════════════════════════════════════
#  DEV — full stack in one terminal
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: dev

dev: infra-up
	@echo "$(BOLD)[backend] Starting…$(RESET)"
	@cd $(BACKEND_DIR) && ../$(UVICORN) app.main:app --port 8000 --reload >> /tmp/autodev-backend.log 2>&1 & \
		echo $$! > /tmp/autodev-backend.pid
	@sleep 2
	@echo "$(BOLD)[worker] Starting…$(RESET)"
	@cd $(BACKEND_DIR) && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
		../$(RQ) worker pipeline:default pipeline:agents --url redis://localhost:6379 >> /tmp/autodev-worker.log 2>&1 & \
		echo $$! > /tmp/autodev-worker.pid
	@echo "$(BOLD)[frontend] Starting…$(RESET)"
	@cd $(FRONTEND_DIR) && npm run dev >> /tmp/autodev-frontend.log 2>&1 & \
		echo $$! > /tmp/autodev-frontend.pid
	@echo ""
	@echo "$(GREEN)$(BOLD)AutoDev running$(RESET)"
	@echo "  UI:       http://localhost:3000"
	@echo "  API:      http://localhost:8000"
	@echo "  API docs: http://localhost:8000/docs"
	@echo ""
	@echo "  Logs:  tail -f /tmp/autodev-backend.log"
	@echo "         tail -f /tmp/autodev-worker.log"
	@echo "         tail -f /tmp/autodev-frontend.log"
	@echo ""
	@echo "  Stop:  make stop"
	@echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  STOP
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: stop

stop:
	@echo "$(BOLD)Stopping all services…$(RESET)"
	@-cat /tmp/autodev-backend.pid  2>/dev/null | xargs kill 2>/dev/null; rm -f /tmp/autodev-backend.pid
	@-cat /tmp/autodev-worker.pid   2>/dev/null | xargs kill 2>/dev/null; rm -f /tmp/autodev-worker.pid
	@-cat /tmp/autodev-frontend.pid 2>/dev/null | xargs kill 2>/dev/null; rm -f /tmp/autodev-frontend.pid
	@-lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@-lsof -ti:3000 | xargs kill -9 2>/dev/null || true
	@docker compose stop
	@echo "$(GREEN)All services stopped$(RESET)"

# ══════════════════════════════════════════════════════════════════════════════
#  TEST
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: test

test:
	@cd $(BACKEND_DIR) && ../$(PYTHON) -m pytest -v

# ══════════════════════════════════════════════════════════════════════════════
#  CLEAN
# ══════════════════════════════════════════════════════════════════════════════
.PHONY: clean

clean:
	@echo "$(BOLD)Cleaning build artifacts…$(RESET)"
	@rm -rf $(BACKEND_DIR)/venv
	@rm -rf $(BACKEND_DIR)/__pycache__ $(BACKEND_DIR)/app/**/__pycache__
	@rm -rf $(BACKEND_DIR)/.pytest_cache $(BACKEND_DIR)/.mypy_cache
	@rm -rf $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/dist
	@find . -name "*.pyc" -delete
	@echo "$(GREEN)Clean done$(RESET)"
