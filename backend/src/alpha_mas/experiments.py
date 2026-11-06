"""Two small, frozen workloads. These are lab controls, not new coordination patterns."""

from typing import TypedDict

from alpha_mas.models import Factor, ResearchFinding, ReviewDecision
from alpha_mas.research.tools import ResearchTools


class Case(TypedDict):
    name: str
    prompt: str
    candidates: list[Factor]
    description: str


CASES: dict[str, Case] = {
    "independent-work-v1": {
        "name": "Independent work",
        "prompt": "Evaluate momentum, earnings and news for 5-day returns. Inspect temporal "
        "evidence, review every candidate and recommend only supported versions.",
        "candidates": ["momentum", "earnings", "sentiment"],
        "description": "Same three candidates; compare sequential and parallel tools "
        "against scoped workers.",
    },
    "review-repair-v1": {
        "name": "Review and repair",
        "prompt": "Evaluate the earnings snapshot and momentum candidates for 5-day returns. "
        "Inspect selected source versions against decision timestamps. Review and repair any "
        "temporal violations before proposing recommendations.",
        "candidates": ["earnings_snapshot", "momentum"],
        "description": "An earnings revision ledger requires point-in-time inspection. "
        "Backtest metrics do not certify validity.",
    },
}


def finding_context(finding: ResearchFinding) -> dict:
    return {
        "finding_id": finding.finding_id,
        "candidate_id": finding.candidate_id,
        "version": finding.version,
        "factor": finding.hypothesis.factor,
        "evidence": [e.model_dump() for e in finding.evidence],
        "result": {"test_ic": finding.result.test_ic, "net_return": finding.result.net_return},
    }


def publication(
    finding: ResearchFinding, reviews: list[ReviewDecision], tools: ResearchTools
) -> dict:
    """Apply one deterministic publication boundary after model recommendations are recorded."""
    checks = tools.temporal_gate(finding.hypothesis.factor)
    matching = [
        r
        for r in reviews
        if r.finding_id == finding.finding_id
        and r.version == finding.version
        and r.candidate_id == finding.candidate_id
    ]
    state = (
        "known_invalid"
        if not all(checks.values())
        else ("verified_valid" if matching and matching[-1].verdict == "accepted" else "unverified")
    )
    return {
        "finding_id": finding.finding_id,
        "candidate_id": finding.candidate_id,
        "version": finding.version,
        "state": state,
        "objective_checks": checks,
        "review_verdict": matching[-1].verdict if matching else None,
    }
