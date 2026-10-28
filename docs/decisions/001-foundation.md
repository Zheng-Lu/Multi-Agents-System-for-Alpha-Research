# ADR 001: explicit async mechanisms and conservative model profiles

Date: 2026-10-28. Status: accepted for the initial increment.

Use direct asyncio control flow for baseline, revision loops and temporary parallel workers.
A graph framework would add little checkpoint value before durable resume semantics are designed.
Trade-off: no LangGraph checkpoint resumption yet. Keep each mechanism in its own module.

Use direct httpx adapters and a shared Chat wire translator with provider-specific options.
Use native OpenAI Responses and Anthropic Messages. Trade-off: token streaming and some model
parameters are deliberately rejected until their wire formats are tested. JSON mode is locally
schema-validated; it is not presented as a vendor strict-schema guarantee.

Store model capabilities/prices outside role and pattern code. Only GLM has recoverable reference
rates in the fetched documentation snapshot. Other live models require explicit price configuration.
This sacrifices convenience to avoid unknown cost silently bypassing a hard allowance.

Use SQLite, immutable artifact records and short transactions for local reproducibility. Add
versioned collaborative state, leases and Redis Streams as separate mechanisms in later increments.
Do not repurpose the trace log as a fake message bus.
