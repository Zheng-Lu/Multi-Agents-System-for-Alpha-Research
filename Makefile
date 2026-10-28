UV := $(shell command -v uv 2>/dev/null || echo .venv/bin/uv)
.PHONY: setup dev api build demo check test evaluate
setup:
	$(UV) sync --locked
	npm ci --prefix frontend
dev:
	npm run dev --prefix frontend
api:
	$(UV) run uvicorn alpha_mas.api.app:app --host 127.0.0.1 --port 8000
build:
	npm run build --prefix frontend
demo: build api
check:
	$(UV) run ruff check backend scripts
	$(UV) run ruff format --check backend scripts
	$(UV) run mypy
	npm run format:check --prefix frontend
	npm run lint --prefix frontend
test:
	$(UV) run pytest -q
	npm test --prefix frontend
evaluate:
	$(UV) run python scripts/evaluate.py
