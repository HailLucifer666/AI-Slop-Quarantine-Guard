.PHONY: dev test lint web help

help:
	@echo "AI Slop Quarantine Guard — Local Development"
	@echo ""
	@echo "make dev   - Start API + worker + postgres + redis (docker-compose up)"
	@echo "make test  - Run pytest on api/"
	@echo "make lint  - Run ruff on api/"
	@echo "make web   - Start Next.js dev server (cd web && npm run dev)"

dev:
	cd infra && docker-compose up

test:
	cd api && pytest -v

lint:
	ruff check api/

web:
	cd web && npm run dev
