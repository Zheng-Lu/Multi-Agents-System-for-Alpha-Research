"""Common bounded research/review primitive; callers own context and handoff decisions."""

from alpha_mas.models import ResearchFinding
from alpha_mas.runtime import Runtime, Session


async def investigate(
    runtime: Runtime,
    researcher: Session,
    reviewer: Session,
    factor: str,
    initial: ResearchFinding | None = None,
) -> list[ResearchFinding]:
    findings = []
    feedback: list[str] = []
    previous = None
    for attempt in range(1, runtime.run.request.max_revisions + 1):
        repair = "earnings_asof" if factor == "earnings_snapshot" else factor
        finding = (
            initial
            if attempt == 1 and initial is not None
            else await runtime.research(
                researcher,
                factor if attempt == 1 else repair,
                feedback,
                candidate_id=factor,
                previous=previous,
                compact=False,
                allow_factor_choice=attempt > 1,
                choices=[factor, repair] if attempt > 1 else [factor],
            )
        )
        findings.append(finding)
        handoff = runtime.emit(
            "handoff.candidate" if researcher is not reviewer else "review.started",
            task=researcher.task,
            parent=researcher.parent,
            metadata={
                "recipient": reviewer.task.agent.agent_id,
                "finding_id": finding.finding_id,
                "candidate_id": factor,
                "version": finding.version,
                "review_mode": "self" if researcher is reviewer else "independent",
                "evidence": [e.model_dump() for e in finding.evidence],
            },
        )
        review, review_event = await runtime.review(reviewer, finding, parent=handoff)
        researcher.retain_finding(finding)
        if reviewer is not researcher:
            reviewer.retain_finding(finding)
        if review.verdict != "rejected":
            break
        previous, feedback = finding, review.observations
        runtime.emit(
            "revision.requested",
            task=researcher.task,
            parent=review_event,
            metadata={
                "finding_id": finding.finding_id,
                "version": finding.version,
                "feedback": feedback,
                "attempts_remaining": runtime.run.request.max_revisions - attempt,
            },
        )
    else:
        runtime.emit(
            "verification.exhausted",
            task=reviewer.task,
            parent=reviewer.parent,
            metadata={"candidate_id": factor, "maximum_attempts": len(findings)},
        )
    return findings
