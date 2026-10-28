import asyncio

from alpha_mas.models import ResearchFinding
from alpha_mas.runtime import Runtime, Session


async def execute(runtime: Runtime) -> None:
    lead = Session(
        runtime, "lead", "Decompose the request, dispatch bounded workers, synthesize evidence"
    )
    _, results = await lead.ask(
        {"phase": "plan", "request": runtime.run.request.task.prompt}, ["delegate_research"]
    )
    plans = [r for r in results if r["tool"] == "delegate_research"]
    if not plans:
        raise ValueError("Lead must submit a validated decomposition using delegate_research")
    families = list(dict.fromkeys(plans[-1]["result"]["families"]))
    findings: list[ResearchFinding] = []

    async def worker(family: str) -> None:
        handoff = runtime.emit(
            "handoff.delegated",
            task=lead.task,
            parent=lead.parent,
            metadata={"recipient": family + "_researcher", "scope": family},
        )
        session = Session(
            runtime, family + "_researcher", f"Evaluate only {family}", parent=handoff
        )
        finding = await runtime.research(session, family)
        findings.append(finding)
        session.complete("Bounded assignment complete; worker context ends.")
        runtime.emit(
            "handoff.returned",
            task=session.task,
            parent=session.parent,
            metadata={
                "recipient": "lead",
                "factor": family,
                "evidence": [e.model_dump() for e in finding.evidence],
            },
        )

    # TaskGroup cancels siblings on failure; no detached workers continue paid inference.
    async with asyncio.TaskGroup() as group:
        for family in families:
            group.create_task(worker(family))
    await runtime.report(lead, sorted(findings, key=lambda f: f.hypothesis.factor))
