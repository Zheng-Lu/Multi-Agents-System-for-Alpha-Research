from alpha_mas.runtime import Runtime, Session


async def execute(runtime: Runtime) -> None:
    session = Session(runtime, "lead", "One context; investigate all three research families")
    findings = [
        await runtime.research(session, family) for family in ["momentum", "earnings", "sentiment"]
    ]
    await runtime.report(session, findings)
