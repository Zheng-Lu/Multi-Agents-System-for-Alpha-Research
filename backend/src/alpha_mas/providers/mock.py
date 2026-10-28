"""Simulates decisions only; every selected tool executes real local calculations."""

import json

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
                        arguments={"families": ["momentum", "earnings", "sentiment"]},
                    )
                ]
                if not results
                else []
            )
            text = "Three bounded investigations delegated."
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
