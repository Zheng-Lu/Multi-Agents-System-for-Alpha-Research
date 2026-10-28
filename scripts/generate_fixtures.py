"""Regenerate synthetic-v1. No external market data or model calls."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1] / "data/fixtures"
root.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20261028)
dates = pd.bdate_range("2023-01-02", periods=300)
prices, earnings, news = [], [], []
for symbol in [f"SYN{i:02d}" for i in range(1, 9)]:
    close = 100.0
    for i, date in enumerate(dates):
        opening = close * np.exp(rng.normal(0, 0.003))
        close = opening * np.exp(rng.normal(0.0001, 0.012))
        prices.append(
            dict(
                symbol=symbol,
                date=str(date.date()),
                open=opening,
                high=max(opening, close) * 1.005,
                low=min(opening, close) * 0.995,
                close=close,
                volume=int(rng.integers(100000, 5000000)),
            )
        )
        if i % 50 == 10:
            earnings.append(
                dict(
                    symbol=symbol,
                    event_at=f"{date.date()}T17:00:00Z",
                    available_at=f"{date.date()}T17:05:00Z",
                    expected_eps=1.0,
                    actual_eps=float(1 + rng.normal(0, 0.2)),
                )
            )
        if i % 7 == 0:
            news.append(
                dict(
                    symbol=symbol,
                    event_at=f"{date.date()}T12:00:00Z",
                    available_at=f"{date.date()}T12:05:00Z",
                    category="synthetic_product_update",
                    sentiment=float(rng.uniform(-1, 1)),
                    headline="SYNTHETIC fixture: product update",
                )
            )
for name, rows in [("prices", prices), ("earnings", earnings), ("news", news)]:
    pd.DataFrame(rows).to_csv(root / f"{name}.csv", index=False, float_format="%.10f")
manifest = dict(
    version="synthetic-v1",
    seed=20261028,
    synthetic=True,
    universe=[f"SYN{i:02d}" for i in range(1, 9)],
    target_days=5,
    files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.csv"))},
)
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
