import asyncio

import numpy as np
import pytest
from alpha_mas.models import BacktestConfig, ResearchArtifact
from alpha_mas.research.tools import ResearchTools
from alpha_mas.storage.sqlite import Store
from pydantic import ValidationError


def test_fixture_reproducibility_costs_and_leakage():
    tools = ResearchTools()
    a = tools.backtest(BacktestConfig(factor="momentum", cost_bps=0))
    b = tools.backtest(BacktestConfig(factor="momentum", cost_bps=100))
    assert a == tools.backtest(BacktestConfig(factor="momentum", cost_bps=0))
    assert b.net_return < a.net_return
    assert a.observations == (300 - 10 - 6) * 8
    assert a.gross_return == a.net_return
    assert np.isclose(a.net_return, np.prod(1 + np.array(a.period_returns)) - 1)
    leak = tools.backtest(BacktestConfig(factor="future_leak"))
    assert leak.leakage_detected and leak.information_coefficient > 0.999
    assert -1 <= a.test_ic <= 1
    assert a.max_drawdown <= 0


def test_after_close_earnings_unavailable_at_same_close():
    tools = ResearchTools()
    panel = tools.panel[tools.panel.symbol == "SYN01"].reset_index(drop=True)
    assert panel.loc[10, "earnings"] == 0
    assert panel.loc[11, "earnings"] != 0
    expected = panel.loc[6, "open"] / panel.loc[1, "open"] - 1
    assert panel.loc[0, "forward"] == pytest.approx(expected)
    # A momentum feature uses only current/past prices, not forward target values.
    assert panel.loc[10, "momentum"] == pytest.approx(
        panel.loc[10, "close"] / panel.loc[0, "close"] - 1
    )


def test_tools_validate_allowlist_and_arguments():
    tools = ResearchTools()
    with pytest.raises(ValueError, match="allowlisted"):
        tools.execute("shell", {"command": "echo unsafe"})
    with pytest.raises(ValidationError):
        tools.execute("run_backtest", {"factor": "momentum", "shell": "bad"})
    with pytest.raises(ValidationError):
        tools.execute("get_price_data", {"symbol": "../secret"})
    assert tools.execute("get_news_events", {})["synthetic"]


async def test_atomic_artifact_idempotency_across_connections(tmp_path):
    path = str(tmp_path / "lab.db")
    stores = [Store(path) for _ in range(5)]
    committed = await asyncio.gather(
        *[
            asyncio.to_thread(
                s.artifact,
                ResearchArtifact(
                    run_id="run",
                    agent_id="agent",
                    kind="backtest",
                    logical_key="same-logical-result",
                    payload={"n": i},
                ),
            )
            for i, s in enumerate(stores)
        ]
    )
    assert len({a.artifact_id for a in committed}) == 1
    assert len(stores[0].artifacts("run")) == 1
    # Simulate process loss after commit: a fresh connection returns the original result.
    original = committed[0]
    recovered = Store(path).artifact(
        ResearchArtifact(
            run_id="run",
            agent_id="agent",
            kind="backtest",
            logical_key="same-logical-result",
            payload={"n": 99},
        )
    )
    assert recovered == original
