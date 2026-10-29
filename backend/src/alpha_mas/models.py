"""Versioned public contracts; provider wire payloads never enter public traces."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def uid() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Pattern(StrEnum):
    BASELINE = "baseline"
    GENERATOR_VERIFIER = "generator_verifier"
    ORCHESTRATOR = "orchestrator_subagent"


class ModelCapabilities(Contract):
    tool_calling: bool = False
    parallel_tool_calls: bool | None = None
    structured_output: bool = False
    streaming: bool = False
    reasoning_mode: bool = False
    max_context_tokens: int | None = None
    max_output_tokens: int | None = Field(default=None, ge=0)


class ModelConfig(Contract):
    provider: str = "mock"
    model: str = "deterministic-v1"
    max_output_tokens: int = Field(default=1500, ge=64, le=8192)
    reasoning: Literal["default", "enabled", "disabled"] = "default"
    stream: bool = False
    response_schema: dict[str, Any] | None = None


class ModelPricing(Contract):
    currency: Literal["USD"] = "USD"
    effective_date: str
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    cached_input_per_million: float | None = Field(default=None, ge=0)
    source: str


class ModelEntry(Contract):
    provider: str
    model: str
    capabilities: ModelCapabilities
    pricing: ModelPricing | None = None
    documentation: str
    verified_on: str
    smoke_tested: bool = False
    notes: str = "Documentation checked; live smoke test pending."


class ModelUsage(Contract):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class ToolCall(Contract):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    # Opaque provider state kept only inside the agent's private in-memory context.
    private_state: dict[str, Any] = Field(default_factory=dict, exclude=True)


class ToolDefinition(Contract):
    name: str
    description: str
    parameters: dict[str, Any]


class ModelResponse(Contract):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: ModelUsage = Field(default_factory=ModelUsage)
    model: str
    finish_reason: str
    private_state: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def as_message(self) -> Message:
        return Message(
            role="assistant",
            content=self.text,
            tool_calls=self.tool_calls,
            private_state=self.private_state,
        )


class ModelAssignments(Contract):
    default: ModelConfig = Field(default_factory=ModelConfig)
    roles: dict[str, ModelConfig] = Field(default_factory=dict)
    fallbacks: dict[str, ModelConfig] = Field(default_factory=dict)
    authorize_fallback_data_transfer: bool = False


class Budget(Contract):
    max_cost_usd: float = Field(default=0.10, ge=0, le=10)
    max_tokens_per_agent: int = Field(default=48000, ge=1, le=200000)
    max_calls_per_agent: int = Field(default=10, ge=1, le=40)
    max_steps: int = Field(default=80, ge=1, le=300)
    max_runtime_seconds: float = Field(default=120, ge=0.01, le=600)
    max_retries: int = Field(default=1, ge=0, le=3)


class ResearchTask(Contract):
    prompt: str = Field(
        default="Evaluate momentum, earnings and news signals for 5-day returns.",
        min_length=3,
        max_length=3000,
    )
    dataset_version: Literal["synthetic-v1"] = "synthetic-v1"
    target_days: Literal[5] = 5


class RunRequest(Contract):
    task: ResearchTask = Field(default_factory=ResearchTask)
    pattern: Pattern = Pattern.BASELINE
    mode: Literal["demo", "live"] = "demo"
    models: ModelAssignments = Field(default_factory=ModelAssignments)
    budget: Budget = Field(default_factory=Budget)
    max_revisions: int = Field(default=2, ge=1, le=4)
    inject_leak: bool = True


class AgentIdentity(Contract):
    agent_id: str
    role: str
    context_id: str = Field(default_factory=uid)
    persistent: bool = False


class AgentTask(Contract):
    task_id: str = Field(default_factory=uid)
    agent: AgentIdentity
    scope: str
    parent_task_id: str | None = None


class ResearchHypothesis(Contract):
    hypothesis_id: str = Field(default_factory=uid)
    factor: str
    rationale: str
    horizon_days: Literal[5] = 5


class EvidenceReference(Contract):
    artifact_id: str
    dataset_version: str = "synthetic-v1"
    description: str


class BacktestConfig(Contract):
    factor: Literal["momentum", "earnings", "sentiment", "combined", "random", "future_leak"]
    cost_bps: float = Field(default=10.0, ge=0, le=1000)
    split_fraction: float = Field(default=0.65, ge=0.4, le=0.8)
    horizon_days: Literal[5] = 5


class BacktestResult(Contract):
    config: BacktestConfig
    dataset_version: str = "synthetic-v1"
    synthetic: bool = True
    observations: int
    information_coefficient: float
    train_ic: float
    test_ic: float
    gross_return: float
    net_return: float
    turnover: float
    max_drawdown: float
    period_returns: list[float]
    leakage_detected: bool
    methodology: str
    limitations: list[str]


class VerificationResult(Contract):
    verdict: Literal["accepted", "rejected", "inconclusive"]
    checks: dict[str, bool]
    feedback: list[str]
    attempt: int


class ResearchFinding(Contract):
    finding_id: str = Field(default_factory=uid)
    hypothesis: ResearchHypothesis
    agent_id: str
    dataset_version: str = "synthetic-v1"
    methodology: str
    evidence: list[EvidenceReference]
    result: BacktestResult
    limitations: list[str]
    uncertainty: str = "Synthetic demonstration; no evidence of real-world profitability."
    status: str = "unverified"
    version: int = 1
    timestamp: str = Field(default_factory=now)


class ResearchArtifact(Contract):
    artifact_id: str = Field(default_factory=uid)
    run_id: str
    agent_id: str
    kind: str
    logical_key: str
    payload: dict[str, Any]
    created_at: str = Field(default_factory=now)


class AgentMessage(Contract):
    message_id: str = Field(default_factory=uid)
    run_id: str
    sender: str
    recipient: str
    topic: str
    content_ref: str
    causation_id: str | None = None


class ExecutionEvent(Contract):
    event_id: str = Field(default_factory=uid)
    run_id: str
    task_id: str | None = None
    agent_id: str | None = None
    parent_event_id: str | None = None
    event_type: str
    timestamp: str = Field(default_factory=now)
    status: str = "completed"
    input_ref: str | None = None
    output_ref: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelInvocationRecord(Contract):
    invocation_id: str = Field(default_factory=uid)
    run_id: str
    task_id: str
    agent_id: str
    pattern: str
    provider: str
    requested_model: str
    actual_model: str | None = None
    original_provider: str
    original_model: str
    usage: ModelUsage = Field(default_factory=ModelUsage)
    estimated_cost_usd: float | None = None
    cost_complete: bool = False
    simulated: bool = False
    latency_ms: float
    retry: int = 0
    status: str
    pricing_effective_date: str | None = None


class RunMetrics(Contract):
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    cost_complete: bool = False
    latency_ms: float = 0
    retries: int = 0
    rate_limit_events: int = 0
    coordination_events: int = 0


class ResearchRun(Contract):
    run_id: str = Field(default_factory=uid)
    request: RunRequest
    status: str = "queued"
    created_at: str = Field(default_factory=now)
    finished_at: str | None = None
    error: str | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
