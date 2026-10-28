from typing import Protocol

from alpha_mas.models import Message, ModelConfig, ModelResponse, ToolDefinition


class ProviderError(Exception):
    """Sanitized error: raw HTTP bodies, headers and request URLs must not escape."""

    def __init__(self, category: str, transient: bool = False):
        self.category = category
        self.transient = transient
        super().__init__(f"Provider request failed ({category})")


class LLMProvider(Protocol):
    async def generate(
        self, messages: list[Message], tools: list[ToolDefinition] | None, config: ModelConfig
    ) -> ModelResponse: ...
