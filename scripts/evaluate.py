"""Credential-free process checks and explicitly controlled architecture comparisons."""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from alpha_mas.comparison import CompareRequest, prepare_comparison, scorecard
from alpha_mas.experiments import CASES
from alpha_mas.models import Pattern, ResearchRun, RunRequest
from alpha_mas.providers.registry import Registry
from alpha_mas.runtime import Runtime
from alpha_mas.storage.sqlite import Store


async def evaluate(repetitions: int, case: str = "legacy", delay: int = 0) -> dict:
    if case != "legacy":
        groups = []
        with tempfile.TemporaryDirectory() as path:
            store = Store(path + "/controlled.db")
            for _ in range(repetitions):
                request = CompareRequest.model_validate(
                    {"case_id": case, "simulated_latency_ms": delay}
                )
                group, runs = prepare_comparison(request)
                store.save_comparison(group)
                # Separate variants avoid inter-run resource contention in timing measurements.
                for run in runs:
                    await Runtime(run, store, Registry()).execute()
                groups.append(scorecard(group, store))
        return {
            "evaluation_version": "controlled-v1",
            "mode": "demo",
            "groups": groups,
            "runs": [row["run"] for group in groups for row in group["rows"]],
            "limitations": "Scripted decisions; token estimates; synthetic market/revision data. "
            "Measures process behavior, not model review reliability or live cost advantage.",
        }
    rows = []
    with tempfile.TemporaryDirectory() as path:
        store = Store(path + "/evaluation.db")
        for repetition in range(repetitions):
            for pattern in Pattern:
                run = ResearchRun(request=RunRequest(pattern=pattern))
                await Runtime(run, store, Registry()).execute()
                artifacts = store.artifacts(run.run_id)
                report = next((a["payload"] for a in artifacts if a["kind"] == "report"), None)
                rows.append(
                    {
                        "repetition": repetition,
                        "pattern": pattern,
                        "status": run.status,
                        "models": run.request.models.model_dump(),
                        "budget": run.request.budget.model_dump(),
                        "metrics": run.metrics.model_dump(),
                        "report_present": report is not None,
                        "evidence_coverage": len(report["findings"]) if report else 0,
                        "invalid_candidate_excluded": bool(report)
                        and "future_leak" not in report["ranked_candidates"],
                        "leak_detected": any(
                            e["event_type"] == "verification.rejected"
                            for e in store.events(run.run_id)
                        ),
                        "computed_results": [
                            {
                                "factor": f["hypothesis"]["factor"],
                                "net_return": f["result"]["net_return"],
                                "test_ic": f["result"]["test_ic"],
                            }
                            for f in report["findings"]
                        ]
                        if report
                        else [],
                    }
                )
    return {
        "evaluation_version": "process-v1",
        "dataset": "synthetic-v1",
        "mode": "demo",
        "controls": "Same fixed task, dataset, tools, Mock Provider and budgets. "
        "Generator-Verifier additionally exercises an injected invalid candidate.",
        "limitations": "Simulated model tokens are approximations. Local wall time is not API "
        "latency. Mechanism-specific coverage differs; these are process checks, "
        "not causal quality rankings or evidence of market alpha.",
        "runs": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/alpha-evaluation.json"))
    parser.add_argument("--repetitions", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--case", choices=["legacy", *CASES], default="legacy")
    parser.add_argument("--simulated-latency-ms", type=int, choices=[0, 100, 250], default=0)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.repetitions, args.case, args.simulated_latency_ms))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {len(result['runs'])} measured runs to {args.output}")
    if any(r["status"] != "completed" for r in result["runs"]):
        raise SystemExit(1)
