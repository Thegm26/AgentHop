.PHONY: help install install-backend install-frontend dev test test-backend test-frontend

PYTHON ?= python3
NPM ?= npm

help:
	@echo "install         Install backend and frontend development dependencies"
	@echo "dev             Run the backend and Vite development servers"
	@echo "test            Run backend and frontend test suites"
	@echo "test-backend    Run backend tests only"
	@echo "test-frontend   Run frontend checks only"

install: install-backend install-frontend

install-backend:
	$(PYTHON) -m pip install -e '.[dev]'

install-frontend:
	$(NPM) --prefix frontend ci

dev:
	./scripts/dev.sh

test: test-backend test-frontend

test-backend:
	$(PYTHON) -m pytest tests/backend

test-frontend:
	$(NPM) --prefix frontend run typecheck
	$(NPM) --prefix frontend run lint
	$(NPM) --prefix frontend test
	$(NPM) --prefix frontend run build
