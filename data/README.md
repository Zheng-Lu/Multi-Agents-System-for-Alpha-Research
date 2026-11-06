# Synthetic fixture provenance

All files under fixtures are generated, fictional research inputs. They are not historical market
data. Version: synthetic-v1, seed: 20261028, 8 fictional equities, 300 business dates.
Regenerate with `uv run python scripts/generate_fixtures.py`; checksums are verified by ResearchTools.

prices.csv: symbol, date, open, high, low, close, volume.
earnings.csv: symbol, event_at, available_at, expected_eps, actual_eps.
news.csv: symbol, event_at, available_at, category, sentiment, headline.

Do not overwrite a published fixture version when changing methodology. Introduce synthetic-v2
and update contracts/tests deliberately. See docs/research-methodology.md for temporal rules.

`challenges/earnings-revisions-v1.csv` is an additional fictional revision ledger, not a change to
synthetic-v1. Regenerate with `uv run python scripts/generate_review_fixture.py`. Its separate
manifest verifies both the source earnings checksum and the new ledger checksum. Fields include
record_id, event_id, symbol, event_at, available_at, version, expected_eps and actual_eps.
Seed 20261104 adds a revised release eight business dates after each original. Neither version
was constructed from future returns. The intentional defect is retrospective revision selection.
