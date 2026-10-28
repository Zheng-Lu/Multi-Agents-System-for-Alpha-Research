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
