# Evaluation

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
quality leaderboard. POST /api/evaluations/compare and persisted experiment management are pending.

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
commit-before-ack fault injection, real-provider smoke and automated live comparison are pending.
The SQLite deduplication test is useful infrastructure coverage, not proof of complete worker recovery.
