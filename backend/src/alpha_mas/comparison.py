"""Persisted four-run comparisons over the two frozen workloads; no paid campaign runner."""

from typing import Literal

from pydantic import Field

from alpha_mas.experiments import CASES
from alpha_mas.models import (
    Budget,
    Contract,
    ExperimentControls,
    Pattern,
    ResearchRun,
    ResearchTask,
    RunRequest,
    now,
    uid,
)
from alpha_mas.storage.sqlite import Store

TERMINAL = {"completed", "failed", "cancelled", "timed_out", "budget_exceeded", "interrupted"}


class CompareRequest(Contract):
    case_id: Literal["independent-work-v1", "review-repair-v1"] = "independent-work-v1"
    budget: Budget = Field(default_factory=lambda: Budget(max_calls_per_agent=40))
    simulated_latency_ms: int = Field(default=0, ge=0, le=1000)


def prepare_comparison(request: CompareRequest) -> tuple[dict, list[ResearchRun]]:
    case = CASES[request.case_id]
    runs = [
        ResearchRun(
            request=RunRequest(
                pattern=pattern,
                task=ResearchTask(prompt=case["prompt"]),
                budget=request.budget.model_copy(deep=True),
                inject_leak=False,
                experiment=ExperimentControls(
                    case_id=request.case_id,
                    parallel_tools=parallel,
                    simulated_latency_ms=request.simulated_latency_ms,
                ),
            )
        )
        for pattern, parallel in [
            (Pattern.BASELINE, False),
            (Pattern.BASELINE, True),
            (Pattern.GENERATOR_VERIFIER, False),
            (Pattern.ORCHESTRATOR, False),
        ]
    ]
    return {
        "comparison_id": uid(),
        "created_at": now(),
        "case_id": request.case_id,
        "request": request.model_dump(),
        "run_ids": [r.run_id for r in runs],
        "protocol_version": "controlled-v1",
        "mode": "demo",
    }, runs


def scorecard(group: dict, store: Store) -> dict:
    rows: list[dict] = []
    required = set(CASES[group["case_id"]]["candidates"])
    for run_id in group["run_ids"]:
        run = store.run(run_id)
        artifacts = store.artifacts(run_id)
        report = next((a["payload"] for a in artifacts if a["kind"] == "report"), None)
        findings = [a["payload"] for a in artifacts if a["kind"] == "finding"]
        covered = {f["candidate_id"] for f in findings if f["evidence"]}
        gates = {g["finding_id"]: g for g in report["publication"]} if report else {}
        proposal = report["agent_proposal"]["finding_ids"] if report else None
        invalid_ids = {i for i, gate in gates.items() if gate["state"] == "known_invalid"}
        reviews = report["reviews"] if report else []
        review_caught = (
            None
            if not report or group["case_id"] != "review-repair-v1"
            else any(
                review["finding_id"] in invalid_ids and review["verdict"] == "rejected"
                for review in reviews
            )
        )
        label = {
            Pattern.BASELINE: "Single Agent · parallel tools"
            if run.request.experiment and run.request.experiment.parallel_tools
            else "Single Agent · sequential",
            Pattern.GENERATOR_VERIFIER: "Generator–Verifier",
            Pattern.ORCHESTRATOR: "Orchestrator–Subagent",
        }[run.request.pattern]
        rows.append(
            {
                "run": run.model_dump(mode="json"),
                "label": label,
                "evidence_coverage": len(covered & required) / len(required),
                "review_caught_issue": review_caught,
                "top_proposed_validity": gates[proposal[0]]["state"]
                if proposal
                else ("no_recommendation" if proposal == [] else "unknown"),
                "published_count": len(report["published_recommendations"]) if report else None,
                "blocked_count": len(report["blocked_recommendations"]) if report else None,
                "repair_completed": any(
                    f["supersedes_finding_id"] in invalid_ids
                    and gates.get(f["finding_id"], {}).get("state") == "verified_valid"
                    for f in findings
                )
                if report
                else None,
            }
        )
    terminal = all(row["run"]["status"] in TERMINAL for row in rows)
    completed = [row for row in rows if row["run"]["status"] == "completed"]
    takeaways = []
    if terminal:
        takeaways.append(
            f"{len(completed)}/{len(rows)} variants completed; every attempt is retained."
        )
        if len(completed) == len(rows):
            states = {r["top_proposed_validity"] for r in completed}
            if len(states) == 1:
                takeaways.append("All variants reached the same top-proposal validity outcome.")
            calls = min(r["run"]["metrics"]["model_calls"] for r in completed)
            labels = [r["label"] for r in completed if r["run"]["metrics"]["model_calls"] == calls]
            takeaways.append(
                f"Fewest model calls: {', '.join(labels)} ({calls}); ties are retained."
            )
        else:
            takeaways.append("Incomplete variants prevent a complete architecture comparison.")
    delay = group["request"]["simulated_latency_ms"]
    takeaways.append(
        f"Wall time includes {delay} ms of simulated delay per model call; "
        "this illustrates concurrency."
        if delay
        else "Zero simulated delay: local timing is not provider latency."
    )
    takeaways.append(
        "Scripted model decisions and estimated demo tokens measure mechanics, "
        "not model quality or live cost advantage."
    )
    return {
        **group,
        "status": "finished" if terminal else "running",
        "case": {"case_id": group["case_id"], **CASES[group["case_id"]]},
        "rows": rows,
        "takeaways": takeaways,
    }
