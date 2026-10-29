import asyncio
import json

import httpx
import pytest
from alpha_mas.api.app import create_app
from alpha_mas.models import (
    Budget,
    ModelAssignments,
    ModelConfig,
    ModelPricing,
    Pattern,
    ResearchRun,
    RunRequest,
)
from alpha_mas.providers.base import ProviderError
from alpha_mas.providers.mock import MockProvider
from alpha_mas.providers.registry import PROVIDERS
from alpha_mas.runtime import Runtime
from alpha_mas.storage.sqlite import Store


@pytest.mark.parametrize("pattern", list(Pattern))
async def test_all_demo_patterns_complete_and_trace_causality(store, registry, pattern):
    # Any accidental network call in Demo Mode fails the test.
    for provider in PROVIDERS:
        if provider != "mock":
            registry.overrides[provider] = FailingProvider()
    run = ResearchRun(request=RunRequest(pattern=pattern))
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    events = store.events(run.run_id)
    ids = set()
    for event in events:
        assert event["run_id"] == run.run_id
        assert event["parent_event_id"] is None or event["parent_event_id"] in ids
        ids.add(event["event_id"])
    artifacts = store.artifacts(run.run_id)
    report = next(a["payload"] for a in artifacts if a["kind"] == "report")
    assert report["synthetic"] and report["findings"]
    if pattern != Pattern.GENERATOR_VERIFIER:
        assert {f["result"]["config"]["factor"] for f in report["findings"]} == {
            "momentum",
            "earnings",
            "sentiment",
        }
        assert len({f["evidence"][0]["artifact_id"] for f in report["findings"]}) == 3
    assert "future_leak" not in report["ranked_candidates"]
    assert run.metrics.model_calls > 0 and run.metrics.tool_calls > 0
    assert run.metrics.estimated_cost_usd == 0
    assert all(i["simulated"] for i in store.invocations(run.run_id))
    # Persistence survives a fresh Store instance.
    assert Store(store.path).run(run.run_id).status == "completed"
    if pattern == Pattern.GENERATOR_VERIFIER:
        assert [v["verdict"] for v in report["verifications"]] == ["rejected", "accepted"]
        assert report["verifications"][0]["feedback"]
        assert [f["result"]["config"]["factor"] for f in report["findings"]] == [
            "future_leak",
            "momentum",
        ]
    if pattern == Pattern.ORCHESTRATOR:
        starts = [e for e in events if e["event_type"] == "agent.started"]
        assert len({s["metadata"]["context_id"] for s in starts}) == 4
        assert all(s["metadata"]["context_policy"].startswith("private") for s in starts)
        assert sum(e["event_type"] == "handoff.returned" for e in events) == 3


async def test_revision_exhaustion_is_terminal(store, registry):
    run = ResearchRun(request=RunRequest(pattern=Pattern.GENERATOR_VERIFIER, max_revisions=1))
    await Runtime(run, store, registry).execute()
    assert run.status == "completed"
    events = store.events(run.run_id)
    assert sum(e["event_type"] == "verification.rejected" for e in events) == 1
    assert any(e["event_type"] == "verification.exhausted" for e in events)
    assert not any(e["event_type"] == "verification.accepted" for e in events)


@pytest.mark.parametrize(
    "budget", [Budget(max_calls_per_agent=1), Budget(max_steps=1), Budget(max_tokens_per_agent=1)]
)
async def test_hard_budgets_stop_execution(store, registry, budget):
    run = ResearchRun(request=RunRequest(budget=budget))
    await Runtime(run, store, registry).execute()
    assert run.status == "budget_exceeded"
    assert run.metrics.model_calls <= 1


class SlowProvider:
    async def generate(self, *args):
        await asyncio.sleep(10)


async def test_timeout_and_cancellation_leave_terminal_records(store, registry):
    registry.overrides["mock"] = SlowProvider()
    run = ResearchRun(request=RunRequest(budget=Budget(max_runtime_seconds=0.02)))
    await Runtime(run, store, registry).execute()
    assert run.status == "timed_out"
    assert store.invocations(run.run_id)[0]["status"] == "cancelled_usage_unknown"
    second = ResearchRun(request=RunRequest())
    runtime = Runtime(second, store, registry)
    job = asyncio.create_task(runtime.execute())
    await asyncio.sleep(0.02)
    runtime.cancelled = True
    job.cancel()
    await job
    assert store.run(second.run_id).status == "cancelled"


class FailingProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, *args):
        self.calls += 1
        raise ProviderError("rate_limit", True)


def live_config(registry, provider):
    entry = next(e for e in registry.entries if e.provider == provider)
    entry.pricing = ModelPricing(
        effective_date="2026-10-28",
        input_per_million=0.1,
        output_per_million=0.2,
        source="internal:test-only",
    )
    return ModelConfig(provider=provider, model=entry.model)


async def test_heterogeneous_assignment_and_provider_changes_need_no_pattern_edits(store, registry):
    glm = live_config(registry, "glm")
    deepseek = live_config(registry, "deepseek")
    registry.overrides.update(glm=MockProvider(), deepseek=MockProvider())
    run = ResearchRun(
        request=RunRequest(
            mode="live",
            pattern=Pattern.ORCHESTRATOR,
            models=ModelAssignments(default=glm, roles={"earnings_researcher": deepseek}),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    records = store.invocations(run.run_id)
    assert {r["provider"] for r in records} == {"glm", "deepseek"}
    assert all(
        r["provider"] == "deepseek" for r in records if r["agent_id"] == "earnings_researcher"
    )
    assert all(not r["simulated"] for r in records)  # adapter injected only within this test
    assert run.metrics.estimated_cost_usd > 0


async def test_retry_is_bounded_and_fallback_explicit(store, registry):
    glm = live_config(registry, "glm")
    deepseek = live_config(registry, "deepseek")
    failing = FailingProvider()
    registry.overrides.update(glm=failing, deepseek=MockProvider())
    assignments = ModelAssignments(
        default=glm, fallbacks={"lead": deepseek}, authorize_fallback_data_transfer=True
    )
    run = ResearchRun(request=RunRequest(mode="live", models=assignments))
    await Runtime(run, store, registry).execute()
    # Fallback is used for each invocation; retry and reservations remain bounded by call limits.
    assert failing.calls <= 10
    records = store.invocations(run.run_id)
    assert records[0]["status"] == "rate_limit"
    assert any(r["provider"] == "deepseek" and r["original_provider"] == "glm" for r in records)
    assert any(e["event_type"] == "model.fallback" for e in store.events(run.run_id))
    assert not run.metrics.cost_complete and run.metrics.estimated_cost_usd is None
    assignments.authorize_fallback_data_transfer = False
    with pytest.raises(ValueError, match="authorization"):
        Runtime(run, store, registry).router.preflight()


async def test_cost_preflight_and_unknown_usage_stop_further_calls(store, registry):
    glm = live_config(registry, "glm")
    registry.overrides["glm"] = MockProvider()
    run = ResearchRun(
        request=RunRequest(
            mode="live", models=ModelAssignments(default=glm), budget=Budget(max_cost_usd=0)
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "budget_exceeded" and run.metrics.model_calls == 0
    registry.entry(glm).pricing = None
    with pytest.raises(ValueError, match="pricing"):
        Runtime(run, store, registry).router.preflight()


async def test_api_lifecycle_replay_saved_models_and_redaction(tmp_path, registry, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "never-expose-this-key")
    app = create_app(str(tmp_path / "api.db"), registry)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/api/health")).json()["status"] == "ok"
            response = await client.post(
                "/api/runs",
                json={
                    "pattern": "generator_verifier",
                    "task": {"prompt": "Do not expose never-expose-this-key"},
                },
            )
            assert response.status_code == 202, response.text
            run = response.json()
            id = run["run_id"]
            for _ in range(100):
                run = (await client.get("/api/runs/" + id)).json()
                if run["status"] in {"completed", "failed"}:
                    break
                await asyncio.sleep(0.03)
            assert run["status"] == "completed", run
            events = (await client.get(f"/api/runs/{id}/events")).json()
            replay = await client.get(f"/api/runs/{id}/stream")
            assert replay.text.count("data: ") == len(events) + 1
            cursor = events[-2]["seq"]
            tail = await client.get(
                f"/api/runs/{id}/stream", headers={"Last-Event-ID": str(cursor)}
            )
            assert tail.text.count("data: ") == 2
            assert "never-expose-this-key" not in json.dumps(run) + replay.text
            for endpoint in [
                "providers",
                "models",
                "research/findings",
                f"runs/{id}/model-usage",
                f"runs/{id}/artifacts",
                f"runs/{id}/metrics",
            ]:
                assert "never-expose-this-key" not in (await client.get("/api/" + endpoint)).text
            config = {
                "name": "Test team",
                "models": {"default": {"provider": "mock", "model": "deterministic-v1"}},
            }
            assert (await client.post("/api/model-configurations", json=config)).status_code == 200
            assert (await client.get("/api/model-configurations")).json()[0]["name"] == "Test team"
            assert (await client.post("/api/runs", json={"mode": "live"})).status_code == 403
            assert (
                await client.post("/api/runs", json={"pattern": "message_bus"})
            ).status_code == 422
            assert (await client.get("/api/runs/missing")).status_code == 404


async def test_restart_marks_inflight_interrupted_without_reinference(tmp_path, registry):
    path = str(tmp_path / "restart.db")
    store = Store(path)
    run = ResearchRun(request=RunRequest(), status="running")
    store.save_run(run)
    app = create_app(path, registry)
    async with app.router.lifespan_context(app):
        assert store.run(run.run_id).status == "interrupted"
        assert not store.invocations(run.run_id)


async def test_worker_budget_failure_preserves_classification(store, registry):
    run = ResearchRun(
        request=RunRequest(
            pattern=Pattern.ORCHESTRATOR,
            models=ModelAssignments(roles={"lead": ModelConfig(max_output_tokens=64)}),
            budget=Budget(max_tokens_per_agent=5000),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "budget_exceeded", run.error
    # The lead has dispatched work; a worker allowance fails inside TaskGroup.
    assert any(e["event_type"] == "handoff.delegated" for e in store.events(run.run_id))


async def test_unknown_provider_usage_stops_next_paid_call(store, registry):
    from alpha_mas.models import ModelResponse, ToolCall

    class UnknownUsage:
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            return ModelResponse(
                model="glm-4.7",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(id="a", name="run_backtest", arguments={"factor": "momentum"})
                ],
            )

    glm = live_config(registry, "glm")
    provider = UnknownUsage()
    registry.overrides["glm"] = provider
    run = ResearchRun(request=RunRequest(mode="live", models=ModelAssignments(default=glm)))
    await Runtime(run, store, registry).execute()
    assert run.status == "budget_exceeded" and provider.calls == 1
    assert "unknown" in run.error
    assert run.metrics.estimated_cost_usd is None and not run.metrics.cost_complete


async def test_openai_unexpected_service_tier_stops_further_calls(store, registry):
    from alpha_mas.models import ModelResponse, ModelUsage, ToolCall

    class DifferentTier:
        calls = 0

        async def generate(self, *args):
            self.calls += 1
            return ModelResponse(
                model="gpt-6-luna",
                finish_reason="completed",
                usage=ModelUsage(input_tokens=100, output_tokens=50),
                private_state={"service_tier": "priority"},
                tool_calls=[
                    ToolCall(id="a", name="run_backtest", arguments={"factor": "momentum"})
                ],
            )

    config = ModelConfig(provider="openai", model="gpt-6-luna")
    provider = DifferentTier()
    registry.overrides["openai"] = provider
    run = ResearchRun(request=RunRequest(mode="live", models=ModelAssignments(default=config)))
    await Runtime(run, store, registry).execute()
    assert run.status == "budget_exceeded" and provider.calls == 1
    assert not run.metrics.cost_complete and run.metrics.estimated_cost_usd is None


async def test_live_baseline_conveys_each_assignment_in_prompt_and_schema(store, registry):
    class ScopedProvider(MockProvider):
        assignments = []

        async def generate(self, messages, tools, config):
            user = next(m for m in reversed(messages) if m.role == "user")
            instruction = json.loads(user.content)
            if instruction["phase"] == "research":
                factor = instruction["factor"]
                self.assignments.append(factor)
                assert f"only factor '{factor}'" in instruction["assignment_constraints"]
                for tool in tools or []:
                    if tool.name in {"run_backtest", "check_data_leakage"}:
                        assert tool.parameters["properties"]["factor"]["enum"] == [factor]
            return await super().generate(messages, tools, config)

    provider = ScopedProvider()
    registry.overrides["openai"] = provider
    run = ResearchRun(
        request=RunRequest(
            mode="live",
            models=ModelAssignments(default=ModelConfig(provider="openai", model="gpt-6-luna")),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    assert provider.assignments == [
        "momentum",
        "momentum",
        "earnings",
        "earnings",
        "sentiment",
        "sentiment",
    ]


async def test_out_of_scope_tool_is_rejected_even_if_model_ignores_schema(store, registry):
    from alpha_mas.models import ModelResponse, ModelUsage, ToolCall

    class IgnoresScope:
        async def generate(self, *args):
            return ModelResponse(
                model="gpt-6-luna",
                finish_reason="completed",
                usage=ModelUsage(input_tokens=10, output_tokens=10),
                tool_calls=[
                    ToolCall(id="bad", name="run_backtest", arguments={"factor": "earnings"})
                ],
            )

    registry.overrides["openai"] = IgnoresScope()
    run = ResearchRun(
        request=RunRequest(
            mode="live",
            models=ModelAssignments(default=ModelConfig(provider="openai", model="gpt-6-luna")),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "failed" and run.metrics.tool_calls == 0
    rejected = next(e for e in store.events(run.run_id) if e["event_type"] == "tool.rejected")
    assert rejected["metadata"]["expected_factor"] == "momentum"
    assert rejected["metadata"]["requested_factor"] == "earnings"
    assert not store.artifacts(run.run_id)


async def test_completed_assignment_compaction_keeps_evidence_and_same_context(store, registry):
    from alpha_mas.runtime import Session

    run = ResearchRun(request=RunRequest())
    runtime = Runtime(run, store, registry)
    session = Session(runtime, "lead", "All families in one context")
    context = session.task.agent.context_id
    first = await runtime.research(session, "momentum")
    assert len(session.messages) == 2
    memory = json.loads(session.messages[-1].content)["completed_assignment_memory"]
    assert memory[0]["evidence"][0]["artifact_id"] == first.evidence[0].artifact_id
    assert memory[0]["net_return"] == first.result.net_return
    assert not session.messages[-1].private_state
    await runtime.research(session, "earnings")
    assert session.task.agent.context_id == context
    assert [f["factor"] for f in session.retained_findings] == ["momentum", "earnings"]
    assert len(session.messages) == 2
    assert len([a for a in store.artifacts(run.run_id) if a["kind"] == "tool_result"]) == 2
    assert sum(e["event_type"] == "context.compacted" for e in store.events(run.run_id)) == 2


async def test_generator_burst_reuses_duplicates_rejects_excess_and_revises(store, registry):
    from alpha_mas.models import ModelResponse, ModelUsage, ToolCall

    class Burst(MockProvider):
        burst_ids = []
        continuation_checked = False

        async def generate(self, messages, tools, config):
            index = max(i for i, m in enumerate(messages) if m.role == "user")
            instruction = json.loads(messages[index].content)
            outputs = messages[index + 1 :]
            if instruction["phase"] == "research" and instruction["factor"] == "future_leak":
                if not outputs:
                    calls = [
                        ToolCall(
                            id="first", name="run_backtest", arguments={"factor": "future_leak"}
                        ),
                        ToolCall(id="other", name="run_backtest", arguments={"factor": "momentum"}),
                        ToolCall(
                            id="same",
                            name="run_backtest",
                            arguments={"factor": "future_leak", "cost_bps": 10},
                        ),
                        *[
                            ToolCall(
                                id=f"p{i}", name="get_price_data", arguments={"symbol": f"SYN0{i}"}
                            )
                            for i in range(1, 8)
                        ],
                    ]
                    self.burst_ids = [c.id for c in calls]
                    return ModelResponse(
                        model=config.model,
                        finish_reason="tool_calls",
                        tool_calls=calls,
                        usage=ModelUsage(input_tokens=10, output_tokens=10),
                    )
                replies = [m for m in outputs if m.role == "tool"]
                assert [m.tool_call_id for m in replies] == self.burst_ids
                assert json.loads(replies[1].content)["error"] == "assignment_already_completed"
                assert json.loads(replies[-1].content)["error"] == "fan_out_limit"
                assert (
                    json.loads(replies[0].content)["artifact_id"]
                    == json.loads(replies[2].content)["artifact_id"]
                )
                assert tools is None
                self.continuation_checked = True
            return await super().generate(messages, tools, config)

    provider = Burst()
    registry.overrides["mock"] = provider
    run = ResearchRun(request=RunRequest(pattern=Pattern.GENERATOR_VERIFIER))
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    assert provider.continuation_checked
    events = store.events(run.run_id)
    assert sum(e["event_type"] == "tool.reused" for e in events) == 1
    assert any(e["event_type"] == "tool.batch_limited" for e in events)
    findings = [a["payload"] for a in store.artifacts(run.run_id) if a["kind"] == "finding"]
    assert [f["hypothesis"]["factor"] for f in findings] == ["future_leak", "momentum"]
    assert [e["event_type"] for e in events if e["event_type"].startswith("verification.")] == [
        "verification.rejected",
        "verification.accepted",
    ]


async def test_openai_burst_preserves_all_native_call_ids_without_duplicate_artifacts(
    store, registry
):
    from alpha_mas.providers.http import OpenAIProvider

    continuations = 0

    def handle(request):
        nonlocal continuations
        payload = json.loads(request.content)
        last = payload["input"][-1]
        if last.get("type") == "function_call_output":
            continuations += 1
            replies = [i for i in payload["input"] if i.get("type") == "function_call_output"]
            calls = [i for i in payload["input"] if i.get("type") == "function_call"]
            assert [i["call_id"] for i in calls] == [i["call_id"] for i in replies]
            assert len(replies) == 10
            assert json.loads(replies[-1]["output"])["error"] == "fan_out_limit"
            assert "tools" not in payload
            output = [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Computed summary"}],
                }
            ]
        elif json.loads(last["content"])["phase"] == "research":
            factor = json.loads(last["content"])["factor"]
            output = [
                {
                    "type": "function_call",
                    "call_id": f"call{i}",
                    "name": "run_backtest",
                    "arguments": json.dumps({"factor": factor}),
                }
                for i in range(10)
            ]
        else:
            output = [
                {"type": "message", "content": [{"type": "output_text", "text": "Final report"}]}
            ]
        return httpx.Response(
            200,
            json={
                "output": output,
                "model": "gpt-6-luna",
                "status": "completed",
                "usage": {"input_tokens": 100, "output_tokens": 100},
            },
        )

    registry.overrides["openai"] = OpenAIProvider(
        "openai", "https://example.test/v1", "fake-key", httpx.MockTransport(handle)
    )
    run = ResearchRun(
        request=RunRequest(
            mode="live",
            models=ModelAssignments(default=ModelConfig(provider="openai", model="gpt-6-luna")),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    assert continuations == 3 and run.metrics.tool_calls == 3
    assert run.metrics.model_calls == 7
    assert sum(a["kind"] == "tool_result" for a in store.artifacts(run.run_id)) == 3


async def test_unique_tool_burst_never_executes_more_than_eight_per_response(store, registry):
    from alpha_mas.models import ModelResponse, ModelUsage, ToolCall
    from alpha_mas.runtime import Session

    class DataBurst:
        async def generate(self, messages, tools, config):
            replies = [m for m in messages if m.role == "tool"]
            if not replies:
                calls = [
                    ToolCall(
                        id=f"price{i}", name="get_price_data", arguments={"symbol": f"SYN0{i}"}
                    )
                    for i in range(1, 9)
                ]
                calls.append(ToolCall(id="news", name="get_news_events", arguments={}))
            elif len(replies) == 9:
                assert json.loads(replies[-1].content)["error"] == "fan_out_limit"
                assert tools  # Required backtest has not run, so it remains available.
                calls = [
                    ToolCall(id="backtest", name="run_backtest", arguments={"factor": "momentum"})
                ]
            else:
                assert tools is None
                calls = []
            return ModelResponse(
                model=config.model,
                text="Summary" if not calls else "",
                tool_calls=calls,
                finish_reason="stop",
                usage=ModelUsage(input_tokens=10, output_tokens=10),
            )

    registry.overrides["mock"] = DataBurst()
    run = ResearchRun(request=RunRequest())
    runtime = Runtime(run, store, registry)
    session = Session(runtime, "lead", "Momentum only")
    _, results = await session.ask(
        {"phase": "research", "factor": "momentum"},
        ["get_price_data", "get_news_events", "run_backtest"],
    )
    assert len(results) == 9  # Eight data reads, then the backtest in a separate response.
    executions = 0
    for event in store.events(run.run_id):
        if event["event_type"] == "model.started":
            executions = 0
        elif event["event_type"] == "tool.completed":
            executions += 1
            assert executions <= 8
    assert not any(r["tool"] == "get_news_events" for r in results)
