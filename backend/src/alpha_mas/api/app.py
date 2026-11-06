import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from alpha_mas.comparison import CompareRequest, prepare_comparison, scorecard
from alpha_mas.experiments import CASES
from alpha_mas.models import (
    Contract,
    ExecutionEvent,
    ModelAssignments,
    ResearchRun,
    RunRequest,
    now,
)
from alpha_mas.providers.registry import ROOT, Registry
from alpha_mas.runtime import Runtime
from alpha_mas.storage.sqlite import Store
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

PATTERNS = [
    {
        "id": "baseline",
        "name": "Single Agent",
        "available": True,
        "mechanism": "One context, common tools, sequential research",
        "official": False,
    },
    {
        "id": "generator_verifier",
        "name": "Generator–Verifier",
        "available": True,
        "mechanism": "Independent checks, structured feedback, bounded revision",
        "official": True,
    },
    {
        "id": "orchestrator_subagent",
        "name": "Orchestrator–Subagent",
        "available": True,
        "mechanism": "Lead decomposes; isolated temporary workers return evidence",
        "official": True,
    },
    {
        "id": "agent_teams",
        "name": "Agent Teams",
        "available": False,
        "mechanism": "Pending: persistent workers, leases, retained context",
        "official": True,
    },
    {
        "id": "message_bus",
        "name": "Message Bus",
        "available": False,
        "mechanism": "Pending: Redis Streams, consumers, retries, replay",
        "official": True,
    },
    {
        "id": "shared_state",
        "name": "Shared State",
        "available": False,
        "mechanism": "Pending: versioned evidence board and cross-agent discovery",
        "official": True,
    },
    {
        "id": "hybrid",
        "name": "Hybrid",
        "available": False,
        "mechanism": "Pending: purposeful composition of the five mechanisms",
        "official": False,
    },
]
TERMINAL = {"completed", "failed", "cancelled", "timed_out", "budget_exceeded", "interrupted"}


class SavedConfiguration(Contract):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9 _-]+$")
    models: ModelAssignments


def create_app(db_path: str | None = None, registry: Registry | None = None) -> FastAPI:
    load_dotenv(ROOT / ".env")
    store = Store(db_path or os.getenv("ALPHA_DB") or str(ROOT / "alpha-lab.db"))
    registry = registry or Registry()
    running: dict[str, tuple[Runtime, asyncio.Task]] = {}
    comparison_active: set[str] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Fail closed after process loss; never automatically repeat a paid inference.
        for item in store.runs():
            if item["status"] not in TERMINAL:
                run = ResearchRun.model_validate(item)
                run.status, run.finished_at = "interrupted", now()
                run.error = (
                    "Server restarted; partial artifacts preserved. Start a new run explicitly."
                )
                store.save_run(run)
                previous = store.events(run.run_id)
                store.event(
                    ExecutionEvent(
                        run_id=run.run_id,
                        event_type="run.interrupted",
                        status="interrupted",
                        parent_event_id=previous[-1]["event_id"] if previous else None,
                        metadata={"error": run.error},
                    )
                )
        yield
        for runtime, task in list(running.values()):
            runtime.cancelled = True
            task.cancel()
        await asyncio.gather(*(t for _, t in running.values()), return_exceptions=True)

    app = FastAPI(title="Alpha Research MAS Lab", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.registry, app.state.running = store, registry, running

    def require(run_id: str) -> ResearchRun:
        try:
            return store.run(run_id)
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0", "dataset": "synthetic-v1"}

    @app.get("/api/patterns")
    async def patterns():
        return PATTERNS

    @app.get("/api/providers")
    async def providers():
        return registry.public_providers()

    @app.get("/api/models")
    @app.get("/api/models/capabilities")
    async def models():
        return [e.model_dump() for e in registry.entries]

    @app.get("/api/model-configurations")
    async def configurations():
        return store.configurations()

    @app.post("/api/model-configurations")
    async def save_configuration(configuration: SavedConfiguration):
        try:
            configs = [
                configuration.models.default,
                *configuration.models.roles.values(),
                *configuration.models.fallbacks.values(),
            ]
            for config in configs:
                registry.validate(config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        store.save_configuration(configuration.name, configuration.models.model_dump())
        return {"saved": configuration.name}

    @app.get("/api/tasks/presets")
    async def presets():
        return [
            {
                "name": "Three research families",
                "prompt": "Evaluate momentum, earnings and news "
                "signals for 5-day returns; compare net performance and held-out IC.",
            },
            {
                "name": "Catch future leakage",
                "prompt": "Review a candidate that mistakenly uses "
                "future returns; revise it and verify the temporal correction.",
            },
            *[{"case_id": case_id, **case} for case_id, case in CASES.items()],
        ]

    def launch(run: ResearchRun, runtime: Runtime, serial: asyncio.Lock | None = None) -> None:
        async def execute():
            if serial is None:
                await runtime.execute()
            else:
                async with serial:
                    await runtime.execute()

        def finished(_: asyncio.Task) -> None:
            running.pop(run.run_id, None)
            comparison_active.discard(run.run_id)

        store.save_run(run)
        task = asyncio.create_task(execute())
        running[run.run_id] = runtime, task
        task.add_done_callback(finished)

    @app.get("/api/evaluations")
    async def evaluations():
        return [scorecard(group, store) for group in store.comparisons()]

    @app.post("/api/evaluations/compare", status_code=202)
    async def compare(request: CompareRequest):
        if running:
            raise HTTPException(
                429, "Finish or cancel active runs before starting a four-run comparison"
            )
        group, runs = prepare_comparison(request)
        runtimes = [Runtime(run, store, registry) for run in runs]
        try:
            for runtime in runtimes:
                runtime.router.preflight()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        store.save_comparison(group)
        serial = asyncio.Lock()
        for run, runtime in zip(runs, runtimes, strict=True):
            comparison_active.add(run.run_id)
            launch(run, runtime, serial)
        return scorecard(group, store)

    @app.get("/api/evaluations/{comparison_id}")
    async def evaluation(comparison_id: str):
        try:
            return scorecard(store.comparison(comparison_id), store)
        except KeyError as exc:
            raise HTTPException(404, "Comparison not found") from exc

    @app.get("/api/runs")
    async def runs():
        return store.runs()

    @app.post("/api/runs", status_code=202)
    async def start(request: RunRequest):
        if request.mode == "live" and os.getenv("ALPHA_ALLOW_LIVE", "false").lower() != "true":
            raise HTTPException(
                403,
                "Live inference disabled. Set ALPHA_ALLOW_LIVE=true server-side "
                "to authorize bounded paid calls.",
            )
        if comparison_active:
            raise HTTPException(
                429, "A controlled comparison is in progress; wait or cancel its runs"
            )
        if len(running) >= 4:
            raise HTTPException(429, "At most four concurrent runs are permitted")
        run = ResearchRun(request=request)
        runtime = Runtime(run, store, registry)
        try:
            runtime.router.preflight()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        launch(run, runtime)
        return store.run(run.run_id)

    @app.get("/api/runs/{run_id}")
    async def run_detail(run_id: str):
        return require(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        run = require(run_id)
        if run_id in running:
            runtime, task = running[run_id]
            runtime.cancelled = True
            if runtime.run.status == "queued":
                runtime.run.status, runtime.run.finished_at = "cancelled", now()
                store.save_run(runtime.run)
                runtime.emit("run.cancelled", status="cancelled")
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return store.run(run_id)
        return run

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, after: int = 0):
        require(run_id)
        return store.events(run_id, after)

    @app.get("/api/runs/{run_id}/stream")
    async def stream(run_id: str, request: Request, after: int = 0):
        require(run_id)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError as exc:
            raise HTTPException(400, "Invalid Last-Event-ID") from exc

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                for event in store.events(run_id, cursor):
                    cursor = event["seq"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if store.run(run_id).status in TERMINAL:
                    yield "event: done\ndata: {}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.15)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/artifacts")
    async def artifacts(run_id: str):
        require(run_id)
        return store.artifacts(run_id)

    @app.get("/api/runs/{run_id}/metrics")
    async def metrics(run_id: str):
        return require(run_id).metrics

    @app.get("/api/runs/{run_id}/model-usage")
    async def usage(run_id: str):
        require(run_id)
        return store.invocations(run_id)

    @app.get("/api/research/findings")
    async def findings():
        return [
            a
            for run in store.runs()
            for a in store.artifacts(run["run_id"])
            if a["kind"] == "finding"
        ]

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=Path(dist), html=True), name="frontend")
    return app


app = create_app()
