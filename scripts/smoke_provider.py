"""Opt-in paid tool-loop smoke test. Never imported or invoked by ordinary CI."""

import argparse
import asyncio

from alpha_mas.models import Budget, ModelAssignments, ModelConfig, Pattern, ResearchRun, RunRequest
from alpha_mas.providers.registry import ROOT, Registry
from alpha_mas.runtime import Runtime
from alpha_mas.security import redact
from alpha_mas.storage.sqlite import Store
from dotenv import load_dotenv

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid", action="store_true", required=True)
    parser.add_argument(
        "--provider",
        choices=["glm", "deepseek", "qwen", "kimi", "openai", "anthropic"],
        required=True,
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--pattern", choices=[p.value for p in Pattern], default="baseline")
    parser.add_argument("--max-cost", type=float, default=0.02)
    parser.add_argument("--max-output-tokens", type=int, default=1500)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    config = ModelConfig(
        provider=args.provider, model=args.model, max_output_tokens=args.max_output_tokens
    )
    run = ResearchRun(
        request=RunRequest(
            mode="live",
            pattern=Pattern(args.pattern),
            models=ModelAssignments(default=config),
            budget=Budget(max_cost_usd=args.max_cost, max_retries=0),
        )
    )
    store = Store(str(ROOT / "alpha-smoke.db"))
    runtime = Runtime(run, store, Registry())
    try:
        runtime.router.preflight()
    except ValueError as exc:
        parser.exit(2, f"Configuration error: {redact(str(exc))}\n")
    asyncio.run(runtime.execute())
    print(store.run(run.run_id).model_dump_json(indent=2))
    if run.status != "completed":
        raise SystemExit(1)
