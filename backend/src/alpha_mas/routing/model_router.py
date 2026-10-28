import asyncio
import json
import time
from collections import defaultdict
from collections.abc import Callable

from alpha_mas.models import (
    AgentTask,
    Message,
    ModelConfig,
    ModelInvocationRecord,
    ModelResponse,
    ModelUsage,
    ResearchRun,
    ToolDefinition,
)
from alpha_mas.providers.base import ProviderError
from alpha_mas.providers.registry import Registry
from alpha_mas.storage.sqlite import Store


class BudgetExceeded(Exception):
    pass


class ModelRouter:
    def __init__(
        self, run: ResearchRun, registry: Registry, store: Store, emit: Callable[..., str]
    ):
        self.run = run
        self.registry = registry
        self.store = store
        self.emit = emit
        self.calls: dict[str, int] = defaultdict(int)
        self.tokens: dict[str, int] = defaultdict(int)
        self.steps = 0
        self.reserved_cost = 0.0
        self.usage_unknown = False
        self.lock = asyncio.Lock()

    def resolve(self, role: str) -> ModelConfig:
        return self.run.request.models.roles.get(role, self.run.request.models.default)

    def step(self) -> None:
        self.steps += 1
        if self.steps > self.run.request.budget.max_steps:
            raise BudgetExceeded("Maximum execution steps reached")

    def preflight(self) -> None:
        request = self.run.request
        configs = [
            request.models.default,
            *request.models.roles.values(),
            *request.models.fallbacks.values(),
        ]
        if request.models.fallbacks and not request.models.authorize_fallback_data_transfer:
            raise ValueError(
                "Fallback requires explicit authorization of provider/region data transfer"
            )
        for config in configs:
            self.registry.validate(config)
            if request.mode == "demo" and config.provider != "mock":
                raise ValueError("Demo Mode requires Mock Provider for every role and fallback")
            if request.mode == "live" and config.provider == "mock":
                raise ValueError("Live Mode requires real provider assignments for every role")
            if request.mode == "live":
                entry = self.registry.entry(config)
                if not entry.pricing:
                    raise ValueError(
                        f"No verified pricing for {config.provider}/{config.model}; "
                        "configure pricing before using a hard cost budget"
                    )
                self.registry.provider(config)

    async def invoke(
        self, task: AgentTask, messages: list[Message], tools: list[ToolDefinition]
    ) -> ModelResponse:
        original = self.resolve(task.agent.role)
        config = original
        fallback_used = False
        retries = 0
        while True:
            entry = self.registry.validate(config, needs_tools=bool(tools))
            # UTF-8 bytes are a conservative local allowance, not provider tokenization.
            input_allowance = len(json.dumps([m.model_dump() for m in messages]).encode())
            input_allowance += len(json.dumps([t.model_dump() for t in tools]).encode()) + 1024
            input_allowance += sum(len(json.dumps(m.private_state).encode()) for m in messages)
            allowance = input_allowance + config.max_output_tokens
            pricing = entry.pricing
            upper_cost = (
                0.0
                if config.provider == "mock"
                else (
                    (
                        input_allowance * pricing.input_per_million
                        + config.max_output_tokens * pricing.output_per_million
                    )
                    / 1e6
                    if pricing
                    else None
                )
            )
            async with self.lock:
                budget = self.run.request.budget
                if self.usage_unknown:
                    raise BudgetExceeded(
                        "Previous usage is unknown; stopping further paid inference"
                    )
                if self.calls[task.agent.agent_id] >= budget.max_calls_per_agent:
                    raise BudgetExceeded("Maximum model calls per agent reached")
                if self.tokens[task.agent.agent_id] + allowance > budget.max_tokens_per_agent:
                    raise BudgetExceeded(
                        "Token allowance exceeds per-agent budget; shorten context"
                    )
                if upper_cost is None or self.reserved_cost + upper_cost > budget.max_cost_usd:
                    raise BudgetExceeded(
                        "Estimated request allowance exceeds remaining cost budget"
                    )
                self.step()
                self.calls[task.agent.agent_id] += 1
                self.tokens[task.agent.agent_id] += allowance
                self.reserved_cost += upper_cost
            parent = self.emit(
                "model.started",
                task=task,
                status="running",
                provider=config.provider,
                model=config.model,
                metadata={"simulated": config.provider == "mock"},
            )
            started = time.monotonic()
            response = None
            failure = None
            try:
                provider = self.registry.provider(config)
                response = await provider.generate(messages, tools or None, config)
            except ProviderError as exc:
                failure = exc
            except asyncio.CancelledError:
                failure = ProviderError("cancelled_usage_unknown")
                raise
            finally:
                usage = response.usage if response else ModelUsage()
                complete = (
                    usage.input_tokens is not None
                    and usage.output_tokens is not None
                    and pricing is not None
                )
                cost = None
                if config.provider == "mock":
                    cost, complete = 0.0, True
                elif complete and pricing:
                    # Cache writes charged conservatively at input rate; native cache-write
                    # tariffs not implemented, so Anthropic cache-write estimates stay incomplete.
                    cached = usage.cached_input_tokens or 0
                    cost = (
                        (usage.input_tokens or 0) * pricing.input_per_million
                        + (usage.output_tokens or 0) * pricing.output_per_million
                    ) / 1e6
                    if cached and pricing.cached_input_per_million is not None:
                        cost -= (
                            cached
                            * (pricing.input_per_million - pricing.cached_input_per_million)
                            / 1e6
                        )
                    if response and response.private_state.get("cache_write_tokens"):
                        complete = False
                if response:
                    async with self.lock:
                        actual = (usage.input_tokens or 0) + (usage.output_tokens or 0)
                        if complete:
                            self.tokens[task.agent.agent_id] += actual - allowance
                            self.reserved_cost += (cost or 0) - upper_cost
                        else:
                            self.usage_unknown = True
                self.store.invocation(
                    ModelInvocationRecord(
                        run_id=self.run.run_id,
                        task_id=task.task_id,
                        agent_id=task.agent.agent_id,
                        pattern=self.run.request.pattern,
                        provider=config.provider,
                        requested_model=config.model,
                        actual_model=response.model if response else None,
                        original_provider=original.provider,
                        original_model=original.model,
                        usage=usage,
                        estimated_cost_usd=cost,
                        cost_complete=complete,
                        simulated=config.provider == "mock",
                        latency_ms=(time.monotonic() - started) * 1000,
                        retry=retries,
                        status="completed"
                        if response
                        else (failure.category if failure else "adapter_error"),
                        pricing_effective_date=pricing.effective_date if pricing else None,
                    )
                )
            if response:
                self.emit(
                    "model.completed",
                    task=task,
                    parent=parent,
                    provider=config.provider,
                    model=response.model,
                    metadata={
                        "finish_reason": response.finish_reason,
                        "usage": usage.model_dump(),
                        "estimated_cost_usd": cost,
                        "cost_complete": complete,
                    },
                )
                if self.tokens[task.agent.agent_id] > budget.max_tokens_per_agent:
                    raise BudgetExceeded("Reported token usage exceeded allowance; run stopped")
                if self.reserved_cost > budget.max_cost_usd:
                    raise BudgetExceeded("Reported estimated cost exceeded budget; run stopped")
                return response
            assert failure
            self.emit(
                "model.failed",
                task=task,
                parent=parent,
                status="failed",
                provider=config.provider,
                model=config.model,
                metadata={"category": failure.category, "retry": retries},
            )
            if failure.transient and retries < budget.max_retries:
                retries += 1
                await asyncio.sleep(min(0.25 * 2**retries, 2))
                continue
            fallback = self.run.request.models.fallbacks.get(task.agent.role)
            if fallback and not fallback_used:
                config = fallback
                fallback_used = True
                self.emit(
                    "model.fallback",
                    task=task,
                    parent=parent,
                    provider=config.provider,
                    model=config.model,
                    metadata={
                        "original_provider": original.provider,
                        "original_model": original.model,
                        "data_transfer_authorized": True,
                    },
                )
                continue
            raise failure
