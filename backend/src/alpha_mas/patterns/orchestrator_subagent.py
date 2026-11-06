import asyncio

from alpha_mas.models import ResearchFinding
from alpha_mas.runtime import Runtime, Session


async def execute(runtime: Runtime) -> None:
    if runtime.run.request.experiment:
        await execute_comparison(runtime)
        return
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


async def execute_comparison(runtime: Runtime) -> None:
    from alpha_mas.experiments import CASES
    from alpha_mas.patterns.review import investigate

    assert runtime.run.request.experiment
    factors: list[str] = list(CASES[runtime.run.request.experiment.case_id]["candidates"])
    lead = Session(runtime, "lead", "Decompose the common workload and synthesize scoped evidence")
    _, results = await lead.ask(
        {
            "phase": "plan",
            "request": runtime.run.request.task.prompt,
            "candidates": factors,
            "permitted_factors": factors,
        },
        ["delegate_research"],
    )
    plans = [r for r in results if r["tool"] == "delegate_research"]
    if (
        not plans
        or set(plans[-1]["result"]["families"]) != set(factors)
        or len(plans[-1]["result"]["families"]) != len(factors)
    ):
        raise ValueError("Controlled decomposition must cover each common candidate exactly once")
    findings: list[ResearchFinding] = []

    async def worker(factor: str) -> None:
        role = ("earnings" if factor.startswith("earnings_") else factor) + "_researcher"
        handoff = runtime.emit(
            "handoff.delegated",
            task=lead.task,
            parent=lead.parent,
            metadata={"recipient": role, "scope": factor},
        )
        session = Session(
            runtime, role, f"Evaluate only {factor}; self-review and bounded repair", parent=handoff
        )
        own_findings = await investigate(runtime, session, session, factor)
        findings.extend(own_findings)
        session.complete("Bounded research/review complete; worker context ends.")
        runtime.emit(
            "handoff.returned",
            task=session.task,
            parent=session.parent,
            metadata={
                "recipient": "lead",
                "factor": factor,
                "finding_ids": [f.finding_id for f in own_findings],
            },
        )

    async with asyncio.TaskGroup() as group:
        for factor in plans[-1]["result"]["families"]:
            group.create_task(worker(factor))
    findings.sort(key=lambda f: (f.candidate_id or "", f.version))
    proposal = await runtime.propose(lead, findings)
    await runtime.report(lead, findings, proposal=proposal)
