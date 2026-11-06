from alpha_mas.runtime import Runtime, Session


async def execute(runtime: Runtime) -> None:
    if runtime.run.request.experiment:
        from alpha_mas.experiments import CASES
        from alpha_mas.patterns.review import investigate

        controls = runtime.run.request.experiment
        factors: list[str] = list(CASES[controls.case_id]["candidates"])
        session = Session(runtime, "lead", "One private context; common workload and self-review")
        initial = (
            await runtime.research_parallel(session, factors) if controls.parallel_tools else []
        )
        findings = []
        for factor in factors:
            finding = next((f for f in initial if f.candidate_id == factor), None)
            findings.extend(await investigate(runtime, session, session, factor, finding))
        proposal = await runtime.propose(session, findings)
        await runtime.report(session, findings, proposal=proposal)
        return
    session = Session(runtime, "lead", "One context; investigate all three research families")
    findings = [
        await runtime.research(session, family) for family in ["momentum", "earnings", "sentiment"]
    ]
    await runtime.report(session, findings)
