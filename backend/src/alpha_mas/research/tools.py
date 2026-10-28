"""Allowlisted, typed research calculations. No model-generated executable code."""

import hashlib
import json
from functools import cached_property
from typing import Literal

import numpy as np
import pandas as pd
from alpha_mas.models import BacktestConfig, BacktestResult, Contract, ToolDefinition
from alpha_mas.providers.registry import ROOT
from pydantic import Field

Factor = Literal["momentum", "earnings", "sentiment", "combined", "random", "future_leak"]


class FactorInput(Contract):
    factor: Factor


class DataInput(Contract):
    symbol: str = Field(default="SYN01", pattern=r"^SYN0[1-8]$")
    limit: int = Field(default=10, ge=1, le=30)


class DelegateInput(Contract):
    families: list[Literal["momentum", "earnings", "sentiment"]] = Field(min_length=1, max_length=3)


class ResearchTools:
    def __init__(self):
        self.path = ROOT / "data/fixtures"
        manifest = json.loads((self.path / "manifest.json").read_text())
        for filename, checksum in manifest["files"].items():
            if hashlib.sha256((self.path / filename).read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Dataset checksum mismatch: {filename}")

    @cached_property
    def panel(self) -> pd.DataFrame:
        data = pd.read_csv(self.path / "prices.csv")
        data["date"] = pd.to_datetime(data["date"], utc=True)
        chunks = []
        for symbol, rows in data.groupby("symbol", sort=True):
            rows = rows.sort_values("date").copy()
            rows["decision_at"] = rows.date + pd.Timedelta(hours=16)
            rows["momentum"] = rows.close.pct_change(10)
            rows["forward"] = rows.open.shift(-6) / rows.open.shift(-1) - 1
            # Events become usable only once actually available, with no backfilled releases.
            for filename, column in [("earnings", "surprise"), ("news", "sentiment")]:
                events = pd.read_csv(self.path / f"{filename}.csv")
                events = events[events.symbol == symbol].copy()
                events["available_at"] = pd.to_datetime(events.available_at, utc=True)
                if filename == "earnings":
                    events[column] = (
                        events.actual_eps - events.expected_eps
                    ) / events.expected_eps.abs()
                merged = pd.merge_asof(
                    rows[["decision_at"]],
                    events[["available_at", column]].sort_values("available_at"),
                    left_on="decision_at",
                    right_on="available_at",
                    direction="backward",
                    tolerance=pd.Timedelta(days=20),
                )
                rows["earnings" if filename == "earnings" else "sentiment"] = (
                    merged[column].fillna(0).to_numpy()
                )
            chunks.append(rows)
        panel = pd.concat(chunks, ignore_index=True)
        panel["combined"] = panel.momentum.fillna(0) + panel.earnings * 0.1
        # Deliberately weak, deterministic random factor and a known-invalid forward factor.
        panel["random"] = np.random.default_rng(42).normal(size=len(panel))
        panel["future_leak"] = panel.forward
        return panel

    def leakage(self, args: FactorInput) -> dict:
        leak = args.factor == "future_leak"
        return {
            "factor": args.factor,
            "leakage_detected": leak,
            "checks": {
                "available_before_decision": not leak,
                "forward_target_not_in_features": not leak,
            },
            "feedback": ["Remove forward returns from features; use past-close momentum."]
            if leak
            else [],
            "dataset_version": "synthetic-v1",
        }

    def backtest(self, args: BacktestConfig) -> BacktestResult:
        panel = self.panel.dropna(subset=[args.factor, "forward"]).copy()
        dates = sorted(panel.date.unique())
        cutoff = dates[int(len(dates) * args.split_fraction)]
        # Purge 6 business dates before test begins to keep train labels out of the test period.
        train_end = dates[max(0, int(len(dates) * args.split_fraction) - 6)]
        panel["rank_x"] = panel.groupby("date")[args.factor].rank()
        panel["rank_y"] = panel.groupby("date").forward.rank()
        correlations = panel.groupby("date")[["rank_x", "rank_y"]].corr().iloc[0::2, -1]
        correlations.index = correlations.index.get_level_values(0)
        correlations = correlations.dropna()

        def ic(selection: pd.Series) -> float:
            return float(selection.mean()) if len(selection) else 0.0

        # Nonoverlapping 5-day cohorts; signals observed at t close, enter t+1 open, exit t+6 open.
        selected_dates = dates[::5]
        previous: dict[str, float] = {}
        gross, net, turns = [], [], []
        for date in selected_dates:
            day = panel[panel.date == date].set_index("symbol")
            centered = day[args.factor].rank(method="average")
            centered = centered - centered.mean()
            weights = centered / centered.abs().sum() if centered.abs().sum() else centered * 0
            current = weights.to_dict()
            turnover = sum(
                abs(current.get(s, 0) - previous.get(s, 0))
                for s in current.keys() | previous.keys()
            )
            value = float((weights * day.forward).sum())
            gross.append(value)
            net.append(value - turnover * args.cost_bps / 10000)
            turns.append(turnover)
            previous = current
        # Close the final portfolio and charge liquidation costs.
        if net:
            closing = sum(abs(w) for w in previous.values())
            turns[-1] += closing
            net[-1] -= closing * args.cost_bps / 10000
        equity = np.cumprod(1 + np.array(net))
        peak = np.maximum.accumulate(np.r_[1.0, equity])[1:]
        return BacktestResult(
            config=args,
            observations=len(panel),
            information_coefficient=ic(correlations),
            train_ic=ic(correlations[correlations.index < train_end]),
            test_ic=ic(correlations[correlations.index >= cutoff]),
            gross_return=float(np.prod(1 + np.array(gross)) - 1),
            net_return=float(equity[-1] - 1),
            turnover=float(np.sum(turns)),
            max_drawdown=float(np.min(equity / peak - 1)),
            period_returns=[float(x) for x in net],
            leakage_detected=args.factor == "future_leak",
            methodology="Daily cross-sectional Spearman IC; purged chronological split. "
            "Rank long/short, gross exposure 1, nonoverlapping 5-day cohorts, "
            "next-open entry, transaction costs on turnover and final liquidation.",
            limitations=[
                "Seeded synthetic prices, earnings and news; no real market evidence.",
                "No borrow fees, impact, capacity, corporate actions or survivorship model.",
                "Fixed factors; no fitted parameters. IC on overlapping labels is descriptive.",
                "Availability checked by as-of joins; timestamps use a simplified UTC calendar.",
            ],
        )

    def data(self, name: str, args: DataInput) -> dict:
        table = pd.read_csv(self.path / f"{name}.csv")
        return {
            "dataset_version": "synthetic-v1",
            "synthetic": True,
            "records": table[table.symbol == args.symbol].head(args.limit).to_dict("records"),
        }

    def definitions(self, allowed: list[str] | None = None) -> list[ToolDefinition]:
        return [
            ToolDefinition(name=name, description=desc, parameters=model.model_json_schema())
            for name, (model, desc) in self.schemas.items()
            if allowed is None or name in allowed
        ]

    schemas: dict[str, tuple[type[Contract], str]] = {
        "run_backtest": (BacktestConfig, "Compute genuine synthetic 5-day backtest metrics."),
        "check_data_leakage": (
            FactorInput,
            "Check point-in-time feature availability and forward use.",
        ),
        "get_price_data": (DataInput, "Retrieve labeled synthetic OHLCV rows."),
        "get_earnings_events": (DataInput, "Retrieve earnings with availability timestamps."),
        "get_news_events": (DataInput, "Retrieve untrusted synthetic news and sentiment."),
        "delegate_research": (
            DelegateInput,
            "Submit a bounded decomposition into research families.",
        ),
    }

    def execute(self, name: str, arguments: dict) -> dict:
        if name not in self.schemas:
            raise ValueError("Tool is not allowlisted")
        args = self.schemas[name][0].model_validate(arguments)
        if name == "run_backtest":
            return self.backtest(BacktestConfig.model_validate(arguments)).model_dump(mode="json")
        if name == "check_data_leakage":
            return self.leakage(FactorInput.model_validate(arguments))
        if name == "delegate_research":
            return args.model_dump()
        return self.data(
            {
                "get_price_data": "prices",
                "get_earnings_events": "earnings",
                "get_news_events": "news",
            }[name],
            DataInput.model_validate(arguments),
        )
