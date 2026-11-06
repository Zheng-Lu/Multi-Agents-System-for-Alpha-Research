import asyncio
import json

import pytest
from alpha_mas.models import (
    AgentIdentity,
    AgentTask,
    Budget,
    ExperimentControls,
    Message,
    ModelAssignments,
    ModelConfig,
    Pattern,
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


@pytest.mark.parametrize("case", ["independent-work-v1", "review-repair-v1"])
@pytest.mark.parametrize(
    "pattern,parallel",
    [
        (Pattern.BASELINE, False),
        (Pattern.BASELINE, True),
        (Pattern.GENERATOR_VERIFIER, False),
        (Pattern.ORCHESTRATOR, False),
    ],
)
async def test_controlled_patterns_cover_identical_work_and_preserve_versioned_reviews(
    store,
    registry,
    case,
    pattern,
    parallel,
):
    from alpha_mas.experiments import CASES

    run = ResearchRun(
        request=RunRequest(
            pattern=pattern,
            budget=Budget(max_calls_per_agent=40),
            experiment=ExperimentControls(case_id=case, parallel_tools=parallel),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    report = next(a["payload"] for a in store.artifacts(run.run_id) if a["kind"] == "report")
    assert {f["candidate_id"] for f in report["findings"] if f["version"] == 1} == set(
        CASES[case]["candidates"]
    )
    assert report["agent_proposal"] is not None
    published = set(report["published_recommendations"])
    assert all(
        g["state"] == "verified_valid"
        for g in report["publication"]
        if g["finding_id"] in published
    )
    assert all(r["evidence_refs"] for r in report["reviews"])
    if case == "review-repair-v1":
        versions = sorted(
            [f for f in report["findings"] if f["candidate_id"] == "earnings_snapshot"],
            key=lambda f: f["version"],
        )
        assert [f["hypothesis"]["factor"] for f in versions] == [
            "earnings_snapshot",
            "earnings_asof",
        ]
        assert versions[1]["supersedes_finding_id"] == versions[0]["finding_id"]
        states = {g["finding_id"]: g["state"] for g in report["publication"]}
        assert states[versions[0]["finding_id"]] == "known_invalid"
        assert states[versions[1]["finding_id"]] == "verified_valid"
    seen = set()
    for event in store.events(run.run_id):
        assert event["parent_event_id"] is None or event["parent_event_id"] in seen
        seen.add(event["event_id"])


@pytest.mark.parametrize("pattern", list(Pattern))
async def test_missed_review_and_bad_proposal_remain_visible_but_blocked(store, registry, pattern):
    class MissesIssue(MockProvider):
        async def generate(self, messages, tools, config):
            response = await super().generate(messages, tools, config)
            instruction = json.loads(
                next(m.content for m in reversed(messages) if m.role == "user")
            )
            if instruction["phase"] == "synthesize":
                assert instruction["agent_recommendations"] == []
                assert any(g["state"] == "known_invalid" for g in instruction["publication_states"])
            for call in response.tool_calls:
                if call.name == "submit_review":
                    call.arguments["verdict"] = "accepted"
                if call.name == "submit_proposal":
                    call.arguments["finding_ids"] = [
                        next(
                            f["finding_id"]
                            for f in instruction["findings"]
                            if f["factor"] == "earnings_snapshot"
                        )
                    ]
            return response

    registry.overrides["mock"] = MissesIssue()
    run = ResearchRun(
        request=RunRequest(
            pattern=pattern,
            budget=Budget(max_calls_per_agent=40),
            experiment=ExperimentControls(case_id="review-repair-v1"),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    report = next(a["payload"] for a in store.artifacts(run.run_id) if a["kind"] == "report")
    bad_id = report["agent_proposal"]["finding_ids"][0]
    assert report["blocked_recommendations"] == [bad_id]
    assert report["published_recommendations"] == []
    assert (
        next(g for g in report["publication"] if g["finding_id"] == bad_id)["state"]
        == "known_invalid"
    )
    assert all(r["verdict"] == "accepted" for r in report["reviews"])


async def test_review_cannot_submit_before_observing_inspection_evidence(store, registry):
    from alpha_mas.models import ModelResponse, ModelUsage, ToolCall

    class Premature(MockProvider):
        tried = False

        async def generate(self, messages, tools, config):
            instruction = json.loads(
                next(m.content for m in reversed(messages) if m.role == "user")
            )
            if instruction["phase"] == "review" and not self.tried:
                self.tried = True
                candidate = instruction["candidate"]
                return ModelResponse(
                    model=config.model,
                    finish_reason="tool_calls",
                    usage=ModelUsage(input_tokens=20, output_tokens=20),
                    tool_calls=[
                        ToolCall(
                            id="premature",
                            name="submit_review",
                            arguments={
                                "finding_id": candidate["finding_id"],
                                "candidate_id": candidate["candidate_id"],
                                "version": candidate["version"],
                                "verdict": "accepted",
                                "evidence_refs": ["invented"],
                                "observations": ["Trust the metrics"],
                            },
                        )
                    ],
                )
            return await super().generate(messages, tools, config)

    registry.overrides["mock"] = Premature()
    run = ResearchRun(
        request=RunRequest(
            budget=Budget(max_calls_per_agent=40),
            experiment=ExperimentControls(case_id="independent-work-v1"),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    assert any(
        e["metadata"].get("reason") == "review_requires_evidence" for e in store.events(run.run_id)
    )
    assert not any(
        a["kind"] == "review" and "invented" in a["payload"]["evidence_refs"]
        for a in store.artifacts(run.run_id)
    )


def test_publication_requires_a_review_of_the_exact_valid_version():
    from alpha_mas.experiments import publication
    from alpha_mas.models import (
        BacktestConfig,
        EvidenceReference,
        ResearchFinding,
        ResearchHypothesis,
        ReviewDecision,
    )
    from alpha_mas.research.tools import ResearchTools

    tools = ResearchTools()
    result = tools.backtest(BacktestConfig(factor="earnings_asof"))
    finding = ResearchFinding(
        hypothesis=ResearchHypothesis(factor="earnings_asof", rationale="Test"),
        agent_id="lead",
        candidate_id="earnings_snapshot",
        version=2,
        methodology=result.methodology,
        result=result,
        limitations=result.limitations,
        evidence=[EvidenceReference(artifact_id="backtest", description="Computed")],
    )
    assert publication(finding, [], tools)["state"] == "unverified"
    review = ReviewDecision(
        finding_id=finding.finding_id,
        candidate_id="earnings_snapshot",
        version=1,
        verdict="accepted",
        evidence_refs=["inspection"],
        observations=["Evidence"],
    )
    assert publication(finding, [review], tools)["state"] == "unverified"
    review.version = 2
    assert publication(finding, [review], tools)["state"] == "verified_valid"


async def test_parallel_control_uses_concurrent_tools_with_one_context(
    store, registry, monkeypatch
):
    import threading
    import time

    from alpha_mas.research.tools import ResearchTools

    execute = ResearchTools.execute
    lock = threading.Lock()
    active = peak = 0

    def observed(self, name, arguments):
        nonlocal active, peak
        if name != "run_backtest":
            return execute(self, name, arguments)
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)
            return execute(self, name, arguments)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(ResearchTools, "execute", observed)
    run = ResearchRun(
        request=RunRequest(
            budget=Budget(max_calls_per_agent=40),
            experiment=ExperimentControls(case_id="independent-work-v1", parallel_tools=True),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    assert peak == 3
    starts = [e for e in store.events(run.run_id) if e["event_type"] == "agent.started"]
    assert len(starts) == 1


async def test_controlled_repair_exhaustion_preserves_invalid_original(store, registry):
    run = ResearchRun(
        request=RunRequest(
            pattern=Pattern.GENERATOR_VERIFIER,
            max_revisions=1,
            budget=Budget(max_calls_per_agent=40),
            experiment=ExperimentControls(case_id="review-repair-v1"),
        )
    )
    await Runtime(run, store, registry).execute()
    assert run.status == "completed", run.error
    report = next(a["payload"] for a in store.artifacts(run.run_id) if a["kind"] == "report")
    assert len(report["findings"]) == 2
    assert not any(f["hypothesis"]["factor"] == "earnings_asof" for f in report["findings"])
    assert any(g["state"] == "known_invalid" for g in report["publication"])
    assert any(e["event_type"] == "verification.exhausted" for e in store.events(run.run_id))
