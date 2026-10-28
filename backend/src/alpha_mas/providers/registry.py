import json
import os
from pathlib import Path

from alpha_mas.models import ModelConfig, ModelEntry
from alpha_mas.providers.base import LLMProvider
from alpha_mas.providers.http import AnthropicProvider, ChatProvider, OpenAIProvider
from alpha_mas.providers.mock import MockProvider

ROOT = Path(__file__).resolve().parents[4]
PROVIDERS = {
    "mock": ("", ""),
    "glm": ("ZAI_API_KEY", "https://api.z.ai/api/paas/v4"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    "qwen": ("DASHSCOPE_API_KEY", ""),
    "kimi": ("MOONSHOT_API_KEY", "https://api.moonshot.ai/v1"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
}


class Registry:
    def __init__(self, path: Path | None = None):
        self.entries = [
            ModelEntry.model_validate(e)
            for e in json.loads((path or ROOT / "config/models.json").read_text())
        ]
        self.overrides: dict[str, LLMProvider] = {}

    def entry(self, config: ModelConfig) -> ModelEntry:
        for e in self.entries:
            if (e.provider, e.model) == (config.provider, config.model):
                return e
        raise ValueError(
            f"Unregistered model {config.provider}/{config.model}; edit config/models.json"
        )

    def validate(self, config: ModelConfig, needs_tools: bool = True) -> ModelEntry:
        entry = self.entry(config)
        cap = entry.capabilities
        if needs_tools and not cap.tool_calling:
            raise ValueError(f"{config.model} does not have validated tool calling")
        if config.stream:
            raise ValueError("Token streaming is not implemented; execution events use SSE")
        if config.response_schema and not cap.structured_output:
            raise ValueError(f"Structured output not validated for {config.model}")
        if config.reasoning != "default" and not cap.reasoning_mode:
            raise ValueError(f"Reasoning override not validated for {config.model}")
        if cap.max_output_tokens and config.max_output_tokens > cap.max_output_tokens:
            raise ValueError("Requested output exceeds registered model limit")
        return entry

    def provider(self, config: ModelConfig) -> LLMProvider:
        if config.provider in self.overrides:
            return self.overrides[config.provider]
        if config.provider == "mock":
            return MockProvider()
        key_var, default_url = PROVIDERS[config.provider]
        key = os.getenv(key_var, "")
        url = os.getenv(f"{config.provider.upper()}_BASE_URL", "") or default_url
        if not key:
            raise ValueError(
                f"Missing {key_var}; use Demo Mode or configure credentials server-side"
            )
        if not url:
            raise ValueError("Set QWEN_BASE_URL to the endpoint matching your key region/workspace")
        if not url.startswith("https://"):
            raise ValueError("Provider base URL must use HTTPS")
        adapters: dict[str, type[OpenAIProvider] | type[AnthropicProvider] | type[ChatProvider]] = {
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
        }
        cls = adapters.get(config.provider, ChatProvider)
        return cls(config.provider, url, key)

    def public_providers(self) -> list[dict]:
        return [
            {
                "provider": p,
                "credentials_present": p == "mock" or bool(os.getenv(k)),
                "endpoint_configured": bool(os.getenv(f"{p.upper()}_BASE_URL") or u),
                "live_enabled": os.getenv("ALPHA_ALLOW_LIVE", "false").lower() == "true",
            }
            for p, (k, u) in PROVIDERS.items()
        ]
