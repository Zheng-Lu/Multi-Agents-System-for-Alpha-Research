import asyncio

import httpx
import pytest
from alpha_mas.api.app import create_app


@pytest.mark.parametrize("case", ["independent-work-v1", "review-repair-v1"])
async def test_comparison_freezes_controls_persists_scores_and_runs_variants_serially(
    tmp_path,
    registry,
    monkeypatch,
    case,
):
    monkeypatch.setenv("ALPHA_ALLOW_LIVE", "true")
    app = create_app(str(tmp_path / "compare.db"), registry)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/evaluations/compare", json={"case_id": case})
            assert response.status_code == 202, response.text
            group = response.json()
            async with asyncio.timeout(30):
                while group["status"] != "finished":
                    await asyncio.sleep(0.01)
                    group = (await client.get(f"/api/evaluations/{group['comparison_id']}")).json()
            rows = group["rows"]
            assert len(rows) == 4 and all(row["run"]["status"] == "completed" for row in rows)
            controls = [row["run"]["request"] for row in rows]
            assert all(
                c["task"] == controls[0]["task"]
                and c["budget"] == controls[0]["budget"]
                and c["models"] == controls[0]["models"]
                for c in controls
            )
            assert all(c["mode"] == "demo" for c in controls)
            assert all(row["evidence_coverage"] == 1 for row in rows)
            assert all(row["top_proposed_validity"] == "verified_valid" for row in rows)
            if case == "review-repair-v1":
                assert all(row["review_caught_issue"] and row["repair_completed"] for row in rows)
            start_finish = []
            for row in rows:
                events = (await client.get(f"/api/runs/{row['run']['run_id']}/events")).json()
                start_finish.append((events[0]["timestamp"], events[-1]["timestamp"]))
            assert all(start_finish[i][1] <= start_finish[i + 1][0] for i in range(3))
            restored = create_app(app.state.store.path, registry)
            assert (
                restored.state.store.comparison(group["comparison_id"])["run_ids"]
                == group["run_ids"]
            )
            assert len((await client.get("/api/evaluations")).json()) == 1
            assert (await client.get("/api/evaluations/missing")).status_code == 404
            # The one-click endpoint never accepts live/provider overrides, even with live opt-in.
            assert (
                await client.post("/api/evaluations/compare", json={"mode": "live"})
            ).status_code == 422


async def test_comparison_retains_budget_failures_instead_of_scoring_only_successes(
    tmp_path, registry
):
    app = create_app(str(tmp_path / "budget.db"), registry)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            group = (
                await client.post(
                    "/api/evaluations/compare", json={"budget": {"max_calls_per_run": 1}}
                )
            ).json()
            async with asyncio.timeout(10):
                while group["status"] != "finished":
                    await asyncio.sleep(0.01)
                    group = (await client.get(f"/api/evaluations/{group['comparison_id']}")).json()
            assert len(group["rows"]) == 4
            assert all(row["run"]["status"] == "budget_exceeded" for row in group["rows"])
            assert all(row["top_proposed_validity"] == "unknown" for row in group["rows"])
            assert any("Incomplete variants" in text for text in group["takeaways"])


async def test_queued_comparison_runs_can_be_cancelled_without_provider_calls(tmp_path, registry):
    class Waiting:
        async def generate(self, *args):
            await asyncio.sleep(10)

    registry.overrides["mock"] = Waiting()
    app = create_app(str(tmp_path / "cancel.db"), registry)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            group = (await client.post("/api/evaluations/compare", json={})).json()
            assert (await client.post("/api/runs", json={})).status_code == 429
            assert (await client.post("/api/evaluations/compare", json={})).status_code == 429
            queued = group["run_ids"][2]
            response = await client.post(f"/api/runs/{queued}/cancel")
            assert response.json()["status"] == "cancelled"
            assert not app.state.store.invocations(queued)
            for run_id in group["run_ids"]:
                await client.post(f"/api/runs/{run_id}/cancel")
            refreshed = (await client.get(f"/api/evaluations/{group['comparison_id']}")).json()
            assert refreshed["status"] == "finished"
