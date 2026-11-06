"""Versioned synthetic earnings ledger; no inference or external data."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(__file__).resolve().parents[1]
source = root / "data/fixtures/earnings.csv"
target = root / "data/challenges"
target.mkdir(exist_ok=True)
rng = np.random.default_rng(20261104)
records = []
for i, row in pd.read_csv(source).iterrows():
    event_id = f"earnings-{i:03d}"
    for version in [1, 2]:
        available = pd.Timestamp(row.available_at)
        if version == 2:
            available += pd.offsets.BDay(8)
        records.append(
            {
                "record_id": f"{event_id}-v{version}",
                "event_id": event_id,
                "symbol": row.symbol,
                "event_at": row.event_at,
                "available_at": available.isoformat(),
                "version": version,
                "expected_eps": row.expected_eps,
                "actual_eps": row.actual_eps + (float(rng.normal(0, 0.08)) if version == 2 else 0),
            }
        )
path = target / "earnings-revisions-v1.csv"
pd.DataFrame(records).to_csv(path, index=False, float_format="%.10f")
(target / "manifest.json").write_text(
    json.dumps(
        {
            "version": "earnings-revisions-v1",
            "synthetic": True,
            "seed": 20261104,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
        },
        indent=2,
    )
    + "\n"
)
