# Evaluation

## Controlled demo comparisons (controlled-v1)

The Compare view and POST `/api/evaluations/compare` run four variants: sequential Single Agent,
Single Agent with concurrent tools in one context, Generator–Verifier, and Orchestrator–Subagent.
GET `/api/evaluations` lists persisted groups; GET `/api/evaluations/{id}` reconstructs a scorecard.
Each group freezes the task, candidates, dataset versions, backtest costs/split, model and complete
budget. Aggregate model-call/token reservations prevent teams receiving extra capacity by headcount.
Variants execute serially, and new runs cannot enter during a comparison, avoiding timing contention.

Two versioned cases:

- `independent-work-v1`: momentum, earnings and sentiment, with review in every variant.
- `review-repair-v1`: an earnings revision snapshot and momentum; repairs preserve candidate identity
  and use explicit finding/version/supersedes references. The as-of factor actually changes values.

Run `uv run python scripts/evaluate.py --case review-repair-v1 --repetitions 2 --output /tmp/review.json`.
Use `--case independent-work-v1` for the independent workload and optionally
`--simulated-latency-ms 100` (or 250). Zero delay is the default. Repeated computed results are
deterministic; timestamps, IDs and wall time are not. JSON results retain every attempt and controls.

Scorecard meanings:

- **Reviewer caught issue**: a model-submitted rejection cites observed inspection evidence for
  the exact invalid finding/version. It is distinct from deterministic publication blocking.
- **Top agent proposal validity**: grading of the first ID in the recorded agent proposal, never
  an inferred recommendation from sorting IC. Bad proposals remain visible, with blocked IDs.
- **Publication**: only valid versions with a matching accepting review can be published.
  Other states are known invalid or unverified. A review of version 1 cannot approve version 2.
- **Evidence coverage**: share of the required candidate identities with computed backtest evidence;
  this is process coverage, not a financial quality score.
- **Peak input tokens**: maximum input count of one invocation per agent, then maximum across agents.
  This is not cumulative context size, effective attention or resident memory. Missing usage is
  unknown. Mock usage is estimated; live usage is provider-reported when available.
- Calls, tool executions, coordination events, local wall time, reported tokens and estimated API
  cost are measured separately. Simulated delay is shown. Budget exhaustion, failure, cancellation,
  interrupted runs, missing reports and ties remain in the cohort.

Every demo reviewer uses the same explicitly scripted timestamp comparison; the demo is not evidence
of empirical reviewer reliability or of typical Single-Agent failure. A common gate can prevent
publication while a model still misses the issue: both outcomes are reported. The injected ledger
is explicitly synthetic, and its backtests do not self-certify temporal validity. No result should
be presented as market profitability. The scorecard produces only observations supported by its data.

The one-click endpoint is Demo-only, even with live server opt-in. Individual controlled live runs
can be configured through `/api/runs`, but have only mocked protocol coverage so far. An automated
live campaign, distributions, equal-cost optimization and a general grading framework remain deferred.

## Historical process checks (process-v1)

Run `uv run python scripts/evaluate.py --repetitions 2 --output /tmp/alpha-evaluation.json`.
A [measured six-run snapshot](samples/process-evaluation.json) is included.
No credentials or paid calls are used. A temporary SQLite database runs all three available patterns,
then the script writes a versioned JSON measurement artifact and exits nonzero if any run failed.

Measured now: completion, report presence, computed finding coverage, invalid-factor exclusion,
explicit rejection events, actual local model/tool invocation counts, approximate simulated tokens,
estimated cost completeness, local latency and computed held-out IC/net returns. Repeated computed
results should be identical; IDs, timestamps and latency deliberately are not deterministic.

The harness labels its controls and limitations. A baseline does not perform an injected revision
exercise; a verifier run has fewer research families. Do not mistake these different workloads for
an equal-task causal estimate. The UI exposes measurements and assignments, not an automated
quality leaderboard. These historical runs remain separate from controlled-v1 comparison groups.

Automated tests cover:

- Three complete credential-free executions and causal parents that refer to earlier events.
- Explicit leaking candidate rejection, computed correction, acceptance, maximum-attempt termination.
- Scoped decomposition and separate worker context IDs.
- Temporal availability, purged target construction, costs, reproducibility and tool argument validation.
- SQLite concurrent logical-artifact deduplication and retry after committed result.
- Six providers' credentials/construction; native/Chat tool continuations; multiple results;
  usage normalization; private state exclusion; HTTP classification; timeout; local schema rejection.
- Capability errors, role overrides, mixed providers, explicit fallback, bounded retry, budget limits.
- Run cancellation, runtime timeout, startup interruption, SSE replay/reconnection, redacted public data.
- Frontend run submission and browser report/graph/replay behavior.

Persistent worker recovery, cross-agent shared-state discovery/conflicts, Redis consumer groups,
commit-before-ack fault injection and automated live comparison are pending. OpenAI's original
baseline/Generator–Verifier loops have live smoke evidence; the new controlled loops do not.
The SQLite deduplication test is useful infrastructure coverage, not proof of complete worker recovery.


Burst regressions additionally check every native OpenAI call ID receives a corresponding result,
that excess requests do not execute, identical normalized arguments reuse evidence, distinct
sequential assignments do not collide after compaction, and one-candidate revision semantics survive
large responses. Tool-call metrics count actual tool executions; reuse/rejection events remain
available in the trace. Browser checks start an isolated Demo Mode server on port 8137 by default
(override with ALPHA_E2E_PORT) and never reuse the user's running lab server.
