# Alpha Research MAS Lab

Python 3.12+, uv, Node 22.12+ (or 24), npm. Work from the repository root.

- Preserve user work. Do not push, deploy, rewrite history or run paid inference without authorization.
- Keep pattern logic independent of provider APIs. All calls go through ModelRouter and LLMProvider.
- Model IDs, capabilities and dated prices belong in config/models.json. Mark unknown prices unknown.
- Demo Mode uses MockProvider exclusively. Never invoke a paid API in ordinary CI.
- Research numbers come only from typed allowlisted tools. Label synthetic evidence everywhere.
- Observe data availability and next-open execution. Never use future targets as accepted features.
- Record causal events and persist artifacts with unique logical keys. Do not claim exactly-once execution.
- Keep credentials and provider reasoning out of client-visible data. Do not log raw HTTP errors.
- Distinguish Anthropic definitions from lab implementation choices. Never advertise pending patterns.
- Use scoped agent contexts; no shared global transcript. Worker failure must cancel sibling tasks.
- Use small validated commits. Do not introduce frameworks without a concrete need.
- Controlled-v1 groups freeze workload/model/backtest settings and aggregate budgets. Preserve the
  single-context parallel-tools control, all failures and three publication states. Reviewing agents
  receive timestamp evidence, never the grading oracle. Never script a baseline failure or MAS win.

Commands:

```sh
uv sync --locked
uv run ruff check backend scripts
uv run ruff format --check backend scripts
uv run mypy
uv run pytest -q
uv run python scripts/evaluate.py --case review-repair-v1 --repetitions 1 --output /tmp/review.json
npm ci --prefix frontend
npm run format:check --prefix frontend
npm run lint --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npm exec --prefix frontend -- playwright install chromium
npm run test:e2e --prefix frontend
uv run uvicorn alpha_mas.api.app:app --host 127.0.0.1 --port 8000
```

Tests: mocked HTTP provider contracts, deterministic research, runtime/API integration, SQLite
idempotency and restart behavior, frontend interaction and browser end-to-end behavior.
See docs/status.md for the exact continuation point and unfulfilled milestone criteria.
