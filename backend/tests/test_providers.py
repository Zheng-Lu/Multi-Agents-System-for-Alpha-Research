import json

import httpx
import pytest
from alpha_mas.models import Message, ModelConfig, ToolDefinition
from alpha_mas.providers.base import ProviderError
from alpha_mas.providers.http import AnthropicProvider, ChatProvider, OpenAIProvider
from alpha_mas.providers.registry import PROVIDERS

TOOL = ToolDefinition(
    name="add",
    description="Add one",
    parameters={
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
        "additionalProperties": False,
    },
)


@pytest.mark.parametrize("provider", ["glm", "deepseek", "qwen", "kimi"])
async def test_chat_multiturn_usage_auth_and_private_reasoning(provider):
    requests = []

    def handle(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "served-model",
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "PRIVATE_OPAQUE_REASONING",
                                "tool_calls": [
                                    {
                                        "id": "a",
                                        "function": {"name": "add", "arguments": '{"n":1}'},
                                    },
                                    {"id": "b", "function": {"name": "add", "arguments": {"n": 2}}},
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "prompt_tokens_details": {"cached_tokens": 3},
                        "completion_tokens_details": {"reasoning_tokens": 4},
                    },
                },
            )
        assert payload["messages"][-3]["reasoning_content"] == "PRIVATE_OPAQUE_REASONING"
        assert [m["tool_call_id"] for m in payload["messages"][-2:]] == ["a", "b"]
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            },
        )

    adapter = ChatProvider(
        provider, "https://example.test/v1", "test-key", httpx.MockTransport(handle)
    )
    config = ModelConfig(provider=provider, model="test-model", reasoning="enabled")
    messages = [Message(role="user", content="add one")]
    first = await adapter.generate(messages, [TOOL], config)
    assert first.model == "served-model"
    assert first.usage.input_tokens == 12 and first.usage.cached_input_tokens == 3
    assert first.usage.reasoning_tokens == 4 and len(first.tool_calls) == 2
    assert "PRIVATE_OPAQUE_REASONING" not in first.model_dump_json()
    messages += [
        first.as_message(),
        Message(role="tool", tool_call_id="a", content="2"),
        Message(role="tool", tool_call_id="b", content="3"),
    ]
    final = await adapter.generate(messages, [TOOL], config)
    assert final.text == "done" and final.usage.input_tokens is None
    assert requests[0].get("enable_thinking", requests[0].get("thinking"))


async def test_openai_native_responses_preserves_output_items():
    output = [
        {"type": "reasoning", "id": "reason", "encrypted_content": "opaque"},
        {
            "type": "function_call",
            "id": "fc",
            "call_id": "call",
            "name": "add",
            "arguments": '{"n":1}',
        },
    ]
    requests = []

    def handle(request):
        assert request.url.path == "/v1/responses"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["store"] is False
        if len(requests) == 2:
            assert payload["input"][1:3] == output
            assert payload["input"][-1]["call_id"] == "call"
        return httpx.Response(
            200,
            json={
                "model": "model",
                "output": output
                if len(requests) == 1
                else [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}],
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    adapter = OpenAIProvider(
        "openai", "https://example.test/v1", "key", httpx.MockTransport(handle)
    )
    config = ModelConfig(provider="openai", model="model")
    messages = [Message(role="user", content="add")]
    first = await adapter.generate(messages, [TOOL], config)
    messages += [first.as_message(), Message(role="tool", tool_call_id="call", content="2")]
    assert (await adapter.generate(messages, [TOOL], config)).text == "done"


async def test_anthropic_native_blocks_and_multiple_results():
    blocks = [
        {"type": "thinking", "thinking": "private", "signature": "signed"},
        {"type": "tool_use", "id": "a", "name": "add", "input": {"n": 1}},
        {"type": "tool_use", "id": "b", "name": "add", "input": {"n": 2}},
    ]
    count = 0

    def handle(request):
        nonlocal count
        count += 1
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "key"
        payload = json.loads(request.content)
        assert payload["system"] == "safe policy"
        if count == 2:
            assert payload["messages"][1]["content"] == blocks
            assert len(payload["messages"][-1]["content"]) == 2
        return httpx.Response(
            200,
            json={
                "content": blocks if count == 1 else [{"type": "text", "text": "done"}],
                "model": "served",
                "stop_reason": "tool_use" if count == 1 else "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
            },
        )

    adapter = AnthropicProvider(
        "anthropic", "https://example.test/v1", "key", httpx.MockTransport(handle)
    )
    config = ModelConfig(provider="anthropic", model="model")
    messages = [Message(role="system", content="safe policy"), Message(role="user", content="add")]
    first = await adapter.generate(messages, [TOOL], config)
    assert first.usage.input_tokens == 13
    assert "signed" not in first.model_dump_json()
    messages += [
        first.as_message(),
        Message(role="tool", tool_call_id="a", content="2"),
        Message(role="tool", tool_call_id="b", content="3"),
    ]
    assert (await adapter.generate(messages, [TOOL], config)).text == "done"


@pytest.mark.parametrize(
    "code,transient,category",
    [(401, False, "http_401"), (429, True, "rate_limit"), (503, True, "http_503")],
)
async def test_errors_are_classified_and_redacted(code, transient, category):
    adapter = ChatProvider(
        "glm",
        "https://example.test",
        "secret",
        httpx.MockTransport(lambda _: httpx.Response(code, json={"error": "secret"})),
    )
    with pytest.raises(ProviderError) as caught:
        await adapter.generate([Message(role="user", content="hi")], None, ModelConfig())
    assert caught.value.transient is transient and caught.value.category == category
    assert "secret" not in str(caught.value)


async def test_timeout_is_transient():
    def handle(request):
        raise httpx.ReadTimeout("secret-url", request=request)

    adapter = ChatProvider("glm", "https://example.test", "key", httpx.MockTransport(handle))
    with pytest.raises(ProviderError, match="timeout_or_network") as caught:
        await adapter.generate([], None, ModelConfig())
    assert caught.value.transient


async def test_structured_output_locally_validated():
    def handle(_):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"n":"wrong"}'}, "finish_reason": "stop"}]},
        )

    adapter = ChatProvider("glm", "https://example.test", "key", httpx.MockTransport(handle))
    config = ModelConfig(
        response_schema={"type": "object", "properties": {"n": {"type": "integer"}}}
    )
    with pytest.raises(ProviderError, match="structured_response_validation"):
        await adapter.generate([], None, config)


@pytest.mark.parametrize("provider", [p for p in PROVIDERS if p != "mock"])
def test_missing_credentials_rejected_and_construction(registry, monkeypatch, provider):
    config = ModelConfig(
        provider=provider, model=next(e.model for e in registry.entries if e.provider == provider)
    )
    with pytest.raises(ValueError, match="Missing"):
        registry.provider(config)
    monkeypatch.setenv(PROVIDERS[provider][0], "test-secret")
    if provider == "qwen":
        with pytest.raises(ValueError, match="QWEN_BASE_URL"):
            registry.provider(config)
        monkeypatch.setenv("QWEN_BASE_URL", "https://region.example/v1")
    assert registry.provider(config).api_key == "test-secret"
    assert "test-secret" not in json.dumps(registry.public_providers())


def test_capabilities_and_unregistered_models(registry):
    with pytest.raises(ValueError, match="Token streaming"):
        registry.validate(ModelConfig(stream=True))
    with pytest.raises(ValueError, match="Structured output"):
        registry.validate(ModelConfig(response_schema={"type": "object"}))
    with pytest.raises(ValueError, match="Unregistered"):
        registry.validate(ModelConfig(provider="glm", model="invented"))
    with pytest.raises(ValueError, match="Reasoning override"):
        registry.validate(ModelConfig(reasoning="enabled"))
