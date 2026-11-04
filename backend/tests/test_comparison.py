import asyncio

from alpha_mas.models import (
    AgentIdentity,
    AgentTask,
    Budget,
    Message,
    ModelAssignments,
    ModelConfig,
    ResearchRun,
    RunRequest,
)
from alpha_mas.providers.mock import MockProvider
from alpha_mas.routing.model_router import BudgetExceeded
from alpha_mas.runtime import Runtime


async def test_concurrent_workers_share_run_call_and_token_reservations(store, registry):
    class SlowMock(MockProvider):
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            await asyncio.sleep(0.02)
            return await super().generate(*args)

    for budget, expected_calls in [
        (Budget(max_calls_per_run=2), 2),
        (Budget(max_tokens_per_run=1500), 1),
    ]:
        provider = SlowMock()
        registry.overrides["mock"] = provider
        run = ResearchRun(
            request=RunRequest(
                budget=budget,
                models=ModelAssignments(default=ModelConfig(max_output_tokens=64)),
            )
        )
        runtime = Runtime(run, store, registry)
        results = await asyncio.gather(
            *[
                runtime.router.invoke(
                    AgentTask(
                        agent=AgentIdentity(agent_id=f"worker-{i}", role="worker"), scope="test"
                    ),
                    [Message(role="user", content='{"phase": "synthesize"}')],
                    [],
                )
                for i in range(4)
            ],
            return_exceptions=True,
        )
        assert provider.calls == expected_calls
        assert sum(isinstance(r, BudgetExceeded) for r in results) == 4 - expected_calls


async def test_run_metrics_peak_input_is_per_invocation_not_sum(store, registry):
    run = ResearchRun(request=RunRequest())
    runtime = Runtime(run, store, registry)
    await runtime.execute()
    records = store.invocations(run.run_id)
    peak = max(r["usage"]["input_tokens"] for r in records)
    assert run.metrics.usage_complete
    assert run.metrics.peak_input_tokens == peak
    assert run.metrics.peak_input_tokens_by_agent == {"lead": peak}
    assert peak < run.metrics.input_tokens
