# Research methodology

Dataset `synthetic-v1`: 300 business dates from 2023-01-02, eight fictional SYN01–SYN08 equities,
seed 20261028. All OHLCV, earnings, analyst expectations and news are invented fixtures, visibly
labeled synthetic. `data/fixtures/manifest.json` records checksums. `scripts/generate_fixtures.py`
recreates the CSVs. Checksum mismatch blocks tools. These data establish process reproducibility,
not market predictability.

Features: 10-close momentum; normalized earnings surprise; timestamped synthetic news sentiment;
a fixed momentum+earnings combination; a weak random factor. The future_leak control explicitly
uses the forward label as a feature. It can be backtested to demonstrate failure but always fails
the integrity gate and is excluded from report rankings. Only these enumerated factors can execute.
This gate is not a general proof that arbitrary user code is leakage-free; arbitrary code is disallowed.

Decision time is 16:00 UTC on each fixture business date. Earnings/news enter as-of backward joins
on available_at, with 20-day expiry. After-close earnings cannot affect that day's signal. Prices at
current close are available for next-open entry. Target: open[t+6]/open[t+1]-1, five trading intervals.
The synthetic UTC calendar is simplified; it is not an exchange calendar or realistic publication feed.

Daily cross-sectional Spearman IC uses ranks. Constant-factor dates are excluded. A chronological
65% split reports train/test IC; six boundary business dates are purged from training labels. No
factor parameters are fitted or selected on the test period. Daily labels overlap: IC summaries are
descriptive, without an independence-based significance claim. A zero IC can mean no usable
correlation observations; the present schema does not yet distinguish that case from a measured zero.

Portfolio calculations use a single nonoverlapping cohort every five dates. Demeaned factor ranks
form a gross-exposure-one long/short portfolio. Consecutive cohort turnover, initial entry and final
liquidation incur configured basis-point costs. Gross/net returns compound computed cohort returns;
maximum drawdown includes starting equity 1. Returns cover the complete sample; test_ic alone is
held-out. Do not label the displayed net return an out-of-sample portfolio result.

No slippage, market impact, borrow costs, corporate actions, real survivorship, capacity or liquidity
constraints are modeled. Additional intentional timestamp/correlation defects and fitted alpha
validation are future work. A positive synthetic result is not evidence of investable alpha.
# Earnings revision challenge

`data/challenges/earnings-revisions-v1.csv` is a separate synthetic revision ledger derived from
the original earnings fixture, with a checksum manifest and seeded eight-business-day revisions.
Regenerate it with `uv run python scripts/generate_review_fixture.py`. The original synthetic-v1
market snapshot is unchanged. Revisions are fabricated challenge data, not historical disclosures.

`earnings_snapshot` joins the latest revision at the original release availability. `earnings_asof`
joins each source version at its actual availability. Both compute real backtests against the same
five-day target. Their backtests return `leakage_detected: null`: performance is not a validity check.
`inspect_temporal_alignment` returns selected record IDs, decision times and availability evidence,
without a verdict. A model submits a typed, evidence-citing review for the exact finding/version.
The legacy verdict-returning leakage tool is unavailable in controlled research/review assignments.

After a structured agent proposal is recorded, a common deterministic gate checks all selected
records and forward dependencies. Publication states are `verified_valid`, `known_invalid` and
`unverified`. A review must accept the exact version for a valid candidate to be published. Original
findings, rejected versions, reviewer misses and blocked recommendations remain inspectable.
Repairs have new finding IDs and explicit version/supersedes links; renaming a factor is not a repair.

MockProvider applies the same explicitly scripted timestamp rule in every reviewing role. Demo
success measures coordination and grading mechanics. Only separately authorized live observations
could establish whether independent review catches more issues than self-review.

