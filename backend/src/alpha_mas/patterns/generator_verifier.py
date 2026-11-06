from alpha_mas.models import VerificationResult
from alpha_mas.research.tools import Factor, FactorInput
from alpha_mas.runtime import Runtime, Session


async def execute(runtime: Runtime) -> None:
    if runtime.run.request.experiment:
        from alpha_mas.experiments import CASES
        from alpha_mas.patterns.review import investigate

        generator = Session(
            runtime, "generator", "Generate the common workload and revise from review evidence"
        )
        verifier = Session(
            runtime, "verifier", "Independent review of scoped versions; no generator conversation"
        )
        findings = []
        for candidate_factor in CASES[runtime.run.request.experiment.case_id]["candidates"]:
            findings.extend(await investigate(runtime, generator, verifier, candidate_factor))
        generator.complete("Common candidate workload completed within revision limits.")
        verifier.complete("Versioned review decisions persisted independently of grading.")
        lead = Session(
            runtime, "lead", "Synthesize finding/review handoffs and submit a recommendation"
        )
        proposal = await runtime.propose(lead, findings)
        await runtime.report(lead, findings, proposal=proposal)
        return
    generator = Session(
        runtime, "generator", "Generate and revise a candidate using structured feedback"
    )
    verifier = Session(
        runtime, "verifier", "Independent validation; no generator conversation access"
    )
    feedback: list[str] = []
    verifications = []
    findings = []
    for attempt in range(1, runtime.run.request.max_revisions + 1):
        factor: Factor = (
            "future_leak" if attempt == 1 and runtime.run.request.inject_leak else "momentum"
        )
        # The configured fault is an explicit experimental control, including in Live Mode.
        # On other attempts the live generator may select one factor from the fixed tool catalog.
        inject_now = attempt == 1 and runtime.run.request.inject_leak
        finding = await runtime.research(
            generator,
            factor,
            feedback,
            allow_factor_choice=runtime.run.request.mode == "live" and not inject_now,
        )
        findings.append(finding)
        factor = finding.result.config.factor
        handoff = runtime.emit(
            "handoff.candidate",
            task=generator.task,
            parent=generator.parent,
            metadata={
                "recipient": "verifier",
                "attempt": attempt,
                "factor": finding.hypothesis.factor,
                "evidence": [e.model_dump() for e in finding.evidence],
            },
        )
        _, results = await verifier.ask(
            {"phase": "verify", "factor": factor, "candidate": finding.model_dump(mode="json")},
            ["check_data_leakage"],
        )
        if not results:
            raise ValueError("Verifier did not execute its independent validation tool")
        gate = runtime.tools.leakage(FactorInput(factor=factor))
        accepted = not gate["leakage_detected"] and not finding.result.leakage_detected
        feedback = gate["feedback"]
        verification = VerificationResult(
            verdict="accepted" if accepted else "rejected",
            checks=gate["checks"],
            feedback=feedback,
            attempt=attempt,
        )
        verifications.append(verification)
        runtime.artifact(
            "verifier", "verification", f"verification:{attempt}", verification.model_dump()
        )
        event = runtime.emit(
            "verification." + verification.verdict,
            task=verifier.task,
            parent=handoff,
            metadata=verification.model_dump(),
        )
        if accepted:
            finding.status = "accepted"
            break
        runtime.emit(
            "revision.requested",
            task=generator.task,
            parent=event,
            metadata={
                "feedback": feedback,
                "attempts_remaining": runtime.run.request.max_revisions - attempt,
            },
        )
    else:
        runtime.emit(
            "verification.exhausted",
            parent=verifier.parent,
            metadata={"verdict": "rejected", "maximum_attempts": len(verifications)},
        )
    generator.complete("Generator finished within revision limit.")
    verifier.complete(verifications[-1].verdict)
    lead = Session(runtime, "lead", "Summarize candidates and explicit verification decisions")
    await runtime.report(lead, findings, verifications)
