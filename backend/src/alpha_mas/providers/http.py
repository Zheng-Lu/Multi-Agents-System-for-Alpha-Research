import json
from typing import Any

import httpx
import jsonschema
from alpha_mas.models import (
    Message,
    ModelConfig,
    ModelResponse,
    ModelUsage,
    ToolCall,
    ToolDefinition,
)
from alpha_mas.providers.base import ProviderError


class HTTPProvider:
    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError(f"Missing credentials for {provider}")
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.provider == "anthropic":
            headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        try:
            async with httpx.AsyncClient(
                timeout=30, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.post(self.base_url + path, json=payload, headers=headers)
            if response.status_code >= 400:
                code = response.status_code
                raise ProviderError(
                    "rate_limit" if code == 429 else f"http_{code}",
                    code in {429, 500, 502, 503, 504, 529},
                )
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderError("timeout_or_network", True) from exc
        except (ValueError, httpx.HTTPError) as exc:
            raise ProviderError("invalid_response") from exc

    def validate(self, response: ModelResponse, config: ModelConfig) -> ModelResponse:
        if config.response_schema and not response.tool_calls:
            try:
                jsonschema.validate(json.loads(response.text), config.response_schema)
            except (ValueError, jsonschema.ValidationError) as exc:
                raise ProviderError("structured_response_validation") from exc
        return response


class ChatProvider(HTTPProvider):
    """Shared wire protocol; provider-specific request options stay at this boundary."""

    def wire_message(self, message: Message) -> dict[str, Any]:
        result: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.role == "assistant":
            # Preserve reasoning_content exactly for thinking tool-use continuation.
            result.update(message.private_state.get("chat_fields", {}))
            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in message.tool_calls
                ]
        if message.role == "tool":
            result["tool_call_id"] = message.tool_call_id
        return result

    async def generate(
        self, messages: list[Message], tools: list[ToolDefinition] | None, config: ModelConfig
    ) -> ModelResponse:
        if config.stream:
            raise ValueError("Provider token streaming is not implemented; use execution SSE")
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [self.wire_message(m) for m in messages],
            "max_tokens": config.max_output_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t.model_dump()} for t in tools]
        if config.reasoning != "default":
            enabled = config.reasoning == "enabled"
            if self.provider in {"glm", "kimi", "deepseek"}:
                payload["thinking"] = {"type": "enabled" if enabled else "disabled"}
            elif self.provider == "qwen":
                payload["enable_thinking"] = enabled
        if config.response_schema:
            # JSON mode plus local schema validation; not a native strict-schema guarantee.
            payload["response_format"] = {"type": "json_object"}
        data = await self.post("/chat/completions", payload)
        try:
            choice = data["choices"][0]
            msg = choice["message"]
            usage = data.get("usage") or {}
            calls = []
            for c in msg.get("tool_calls") or []:
                args = c["function"]["arguments"]
                calls.append(
                    ToolCall(
                        id=c["id"],
                        name=c["function"]["name"],
                        arguments=json.loads(args) if isinstance(args, str) else args,
                    )
                )
            response = ModelResponse(
                text=msg.get("content") or "",
                model=data.get("model", config.model),
                tool_calls=calls,
                finish_reason=choice.get("finish_reason") or "unknown",
                usage=ModelUsage(
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    cached_input_tokens=usage.get(
                        "prompt_cache_hit_tokens",
                        (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                    ),
                    reasoning_tokens=(usage.get("completion_tokens_details") or {}).get(
                        "reasoning_tokens"
                    ),
                ),
                private_state={
                    "chat_fields": {k: v for k, v in msg.items() if k == "reasoning_content"}
                },
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("invalid_response") from exc
        return self.validate(response, config)


class OpenAIProvider(HTTPProvider):
    async def generate(
        self, messages: list[Message], tools: list[ToolDefinition] | None, config: ModelConfig
    ) -> ModelResponse:
        items: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "assistant" and "response_output" in m.private_state:
                items.extend(m.private_state["response_output"])
            elif m.role == "tool":
                items.append(
                    {"type": "function_call_output", "call_id": m.tool_call_id, "output": m.content}
                )
            else:
                items.append({"role": m.role, "content": m.content})
        payload: dict[str, Any] = {
            "model": config.model,
            "input": items,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "service_tier": "default",
            "max_output_tokens": config.max_output_tokens,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", **t.model_dump(), "strict": False} for t in tools
            ]
        if config.reasoning != "default":
            raise ValueError("OpenAI reasoning overrides require a model-specific effort profile")
        if config.stream:
            raise ValueError("Provider token streaming not implemented")
        if config.response_schema:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "result",
                    "schema": config.response_schema,
                    "strict": True,
                }
            }
        data = await self.post("/responses", payload)
        try:
            output = data["output"]
            usage = data.get("usage") or {}
            response = ModelResponse(
                text="".join(
                    c.get("text", "")
                    for i in output
                    if i["type"] == "message"
                    for c in i.get("content", [])
                    if c["type"] == "output_text"
                ),
                tool_calls=[
                    ToolCall(id=i["call_id"], name=i["name"], arguments=json.loads(i["arguments"]))
                    for i in output
                    if i["type"] == "function_call"
                ],
                model=data.get("model", config.model),
                finish_reason=data.get("status", "unknown"),
                usage=ModelUsage(
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    cached_input_tokens=(usage.get("input_tokens_details") or {}).get(
                        "cached_tokens"
                    ),
                    reasoning_tokens=(usage.get("output_tokens_details") or {}).get(
                        "reasoning_tokens"
                    ),
                ),
                private_state={"response_output": output, "service_tier": data.get("service_tier")},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("invalid_response") from exc
        return self.validate(response, config)


class AnthropicProvider(HTTPProvider):
    async def generate(
        self, messages: list[Message], tools: list[ToolDefinition] | None, config: ModelConfig
    ) -> ModelResponse:
        conversation: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                item = {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                    ],
                }
            elif m.role == "assistant" and "content_blocks" in m.private_state:
                item = {"role": "assistant", "content": m.private_state["content_blocks"]}
            else:
                item = {"role": m.role, "content": [{"type": "text", "text": m.content}]}
            if conversation and conversation[-1]["role"] == item["role"]:
                conversation[-1]["content"].extend(item["content"])
            else:
                conversation.append(item)
        payload: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_output_tokens,
            "system": "\n".join(m.content for m in messages if m.role == "system"),
            "messages": conversation,
        }
        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        if config.reasoning != "default" or config.response_schema or config.stream:
            raise ValueError(
                "Anthropic profile supports tools/text; requested option not validated"
            )
        data = await self.post("/messages", payload)
        try:
            blocks = data["content"]
            usage = data.get("usage") or {}
            base_input = usage.get("input_tokens")
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_write = usage.get("cache_creation_input_tokens", 0)
            return ModelResponse(
                text="".join(b["text"] for b in blocks if b["type"] == "text"),
                tool_calls=[
                    ToolCall(id=b["id"], name=b["name"], arguments=b["input"])
                    for b in blocks
                    if b["type"] == "tool_use"
                ],
                model=data.get("model", config.model),
                finish_reason=data.get("stop_reason", "unknown"),
                usage=ModelUsage(
                    input_tokens=None
                    if base_input is None
                    else base_input + cache_read + cache_write,
                    output_tokens=usage.get("output_tokens"),
                    cached_input_tokens=cache_read,
                ),
                private_state={"content_blocks": blocks, "cache_write_tokens": cache_write},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("invalid_response") from exc
