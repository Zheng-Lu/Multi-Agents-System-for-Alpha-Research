"""Dated documentation snapshot. Recheck official sources before paid benchmarks."""

import json
from pathlib import Path


def entry(
    provider,
    model,
    doc,
    *,
    price=None,
    reasoning=False,
    structured=False,
    notes="",
    verified_on="2026-10-28",
    smoke_tested=None,
):
    return dict(
        provider=provider,
        model=model,
        documentation=doc,
        verified_on=verified_on,
        smoke_tested=provider == "mock" if smoke_tested is None else smoke_tested,
        notes=notes or "Documentation checked; live smoke pending.",
        capabilities=dict(
            tool_calling=True,
            parallel_tool_calls=True if provider == "mock" else None,
            structured_output=structured,
            streaming=False,
            reasoning_mode=reasoning,
            max_output_tokens=8192,
        ),
        pricing=price,
    )


def price(inp, out, cached, source, effective_date="2026-10-28"):
    return dict(
        currency="USD",
        effective_date=effective_date,
        input_per_million=inp,
        output_per_million=out,
        cached_input_per_million=cached,
        source=source,
    )


entries = [
    entry(
        "mock",
        "deterministic-v1",
        "internal:mock-v1",
        price=price(0, 0, 0, "internal:simulation"),
        notes="Simulated decisions; real research tools.",
    ),
    entry(
        "glm",
        "glm-4.7",
        "https://docs.z.ai/api-reference/llm/chat-completion",
        price=price(0.6, 2.2, 0.11, "https://docs.z.ai/guides/overview/pricing"),
        reasoning=True,
        structured=True,
    ),
    entry(
        "deepseek",
        "deepseek-flash",
        "https://api-docs.deepseek.com/guides/tool_calls/",
        reasoning=True,
        structured=True,
        notes="Current documented alias; pricing unavailable in fetched page. Configure rates.",
    ),
    entry(
        "qwen",
        "qwen-plus",
        "https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope",
        notes="Requires matching QWEN_BASE_URL; pricing is endpoint/tier dependent.",
    ),
    entry(
        "kimi",
        "kimi-k3.1-pro",
        "https://platform.kimi.ai/docs/guide/use-kimi-api-to-complete-tool-calls",
        notes="General inference; pricing unavailable. Reasoning overrides not validated.",
    ),
    entry(
        "openai",
        "gpt-6-luna",
        "https://developers.openai.com/api/docs/models/gpt-6-luna",
        price=price(
            0.1,
            0.5,
            0.01,
            "https://developers.openai.com/api/docs/models/gpt-6-luna",
            effective_date="2026-10-29",
        ),
        verified_on="2026-10-29",
        smoke_tested=True,
        notes="Live baseline smoke-tested 2026-10-29: tools, usage, report. "
        "Standard global short-context pricing. See docs/samples/openai-live-smoke.json.",
    ),
    entry(
        "anthropic",
        "claude-haiku-5-5",
        "https://platform.claude.com/docs/en/models/haiku-5-5/overview",
        notes="Native Messages API. Tiered/cache-write pricing requires explicit local profile.",
    ),
]
(Path(__file__).resolve().parents[1] / "config/models.json").write_text(
    json.dumps(entries, indent=2) + "\n"
)
