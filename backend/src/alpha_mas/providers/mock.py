"""Simulates decisions only; every selected tool executes real local calculations."""

import json
from datetime import datetime

from alpha_mas.models import (
    Message,
    ModelConfig,
    ModelResponse,
    ModelUsage,
    ToolCall,
    ToolDefinition,
)


class MockProvider:
    async def generate(
        self, messages: list[Message], tools: list[ToolDefinition] | None, config: ModelConfig
    ) -> ModelResponse:
        last_user = max(i for i, m in enumerate(messages) if m.role == "user")
        instruction = json.loads(messages[last_user].content)
        phase = instruction["phase"]
        results = [m for m in messages[last_user + 1 :] if m.role == "tool"]
        calls: list[ToolCall] = []
        text = ""
        if phase == "plan":
            calls = (
                [
                    ToolCall(
                        id="plan",
                        name="delegate_research",
                        arguments={
                            "families": instruction.get(
                                "candidates", ["momentum", "earnings", "sentiment"]
                            )
                        },
                    )
                ]
                if not results
                else []
            )
            text = "Three bounded investigations delegated."
        elif phase == "research_batch":
            if not results:
                calls = [
                    ToolCall(
                        id=f"backtest-{factor}", name="run_backtest", arguments={"factor": factor}
                    )
                    for factor in instruction["factors"]
                ]
            else:
                text = "Simulated single-context synthesis of concurrent tool results."
        elif phase == "review":
            observed = [json.loads(m.content) for m in results if "result" in json.loads(m.content)]
            inspection = next((r for r in observed if "samples" in r["result"]), None)
            submitted = any("verdict" in r["result"] for r in observed)
            if not inspection:
                calls = [
                    ToolCall(
                        id="inspect",
                        name="inspect_temporal_alignment",
                        arguments={"factor": instruction["factor"]},
                    )
                ]
            elif not submitted:
                # Explicit scripted evidence rule, identical for self-review and independent review.
                # This demonstrates plumbing, never estimates a model's issue-detection reliability.
                samples = inspection["result"]["samples"]
                invalid = any(
                    datetime.fromisoformat(s["selected_record_available_at"])
                    > datetime.fromisoformat(s["decision_at"])
                    for s in samples
                )
                candidate = instruction["candidate"]
                calls = [
                    ToolCall(
                        id="review",
                        name="submit_review",
                        arguments={
                            "finding_id": candidate["finding_id"],
                            "candidate_id": candidate["candidate_id"],
                            "version": candidate["version"],
                            "verdict": "rejected"
                            if invalid
                            else "accepted"
                            if samples
                            else "inconclusive",
                            "evidence_refs": [inspection["artifact_id"]],
                            "observations": [
                                "Selected records become available after decision_at; "
                                "rebuild with point-in-time source versions."
                                if invalid
                                else "Inspected source availability against decision timestamps."
                            ],
                        },
                    )
                ]
            else:
                text = "Scripted demo review recorded; interpretation is simulated."
        elif phase == "propose":
            if not results:
                accepted = {
                    r["finding_id"] for r in instruction["reviews"] if r["verdict"] == "accepted"
                }
                latest: dict[str, dict] = {}
                for finding in instruction["findings"]:
                    current = latest.get(finding["candidate_id"])
                    if current is None or finding["version"] > current["version"]:
                        latest[finding["candidate_id"]] = finding
                ranked = sorted(
                    [f for f in latest.values() if f["finding_id"] in accepted],
                    key=lambda f: f["result"]["test_ic"],
                    reverse=True,
                )
                calls = [
                    ToolCall(
                        id="proposal",
                        name="submit_proposal",
                        arguments={
                            "finding_ids": [f["finding_id"] for f in ranked],
                            "rationale": "Scripted demo proposal: latest accepted versions, "
                            "ordered by computed held-out IC. No live model judgment is measured.",
                        },
                    )
                ]
            else:
                text = "Scripted proposal persisted."
        elif phase == "research":
            factor = instruction["factor"]
            if not results:
                calls = [ToolCall(id="backtest", name="run_backtest", arguments={"factor": factor})]
            else:
                text = "Simulated decision: tool evidence supports a reproducible synthetic study."
        elif phase == "verify":
            if not results:
                calls = [
                    ToolCall(
                        id="check",
                        name="check_data_leakage",
                        arguments={"factor": instruction["factor"]},
                    )
                ]
            else:
                text = "Simulated independent review: use the deterministic gate's verdict."
        else:
            text = (
                "Simulated synthesis: compare net returns and held-out IC; exclude leaking factors."
            )
        if config.response_schema:
            text = json.dumps({"simulated": True})
            calls = []
        return ModelResponse(
            text=text,
            tool_calls=calls,
            model=config.model,
            finish_reason="tool_calls" if calls else "stop",
            usage=ModelUsage(
                input_tokens=sum(len(m.content) for m in messages) // 4, output_tokens=50
            ),
        )
