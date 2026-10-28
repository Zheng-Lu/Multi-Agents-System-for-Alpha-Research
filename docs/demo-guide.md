# Leadership demonstration — initial increment (10–15 minutes)

Preparation: follow README startup, keep the backend on loopback, use Demo Mode. No internet,
credentials or manual database edits are needed after dependency installation. This demonstrates
three mechanisms, not all five. Use the UI's pending entries to explain the remaining work honestly.

1. **0–2 min: establish the control.** Select Single Agent, run the fixed task. One context uses
   actual backtest tools across momentum, earnings and sentiment. Open Research report and show
   synthetic labels, held-out IC, complete-sample net returns and limitations.
2. **2–5 min: explicit quality gates.** Select Generator–Verifier and run. Inspect separate generator
   and verifier contexts. In Research report, attempt 1 rejects forward-return leakage; attempt 2
   accepts the corrected temporal implementation. Acceptance means integrity, not profitable alpha.
   Evidence & trace exposes feedback, revision and each tool artifact reference.
3. **5–8 min: independent work.** Run Orchestrator–Subagent. The lead submits a decomposition and
   three temporary workers execute independently. Click Earnings: show scope/context ID, assigned
   model and tools. Returned evidence goes to lead synthesis, without shared conversation histories.
4. **8–10 min: model dimension.** Open model assignments. Show one model for every role, overrides,
   saved configurations and mixed-provider candidates. Explain live-unverified labels, unknown price
   rejection and server-side paid opt-in. Return to the credential-free preset before running again.
5. **10–12 min: inspect and compare.** Open Compare to inspect calls, tokens, time, cost completeness
   and explicit assignments/budget. These are descriptive measurements of different workloads.
   Simulated model tokens and zero API cost cannot establish a live-model cost advantage.
6. **12–15 min: replay/reliability and scope.** Reopen a persisted run and click Replay trace. It
   animates stored events, with no new model calls. Show partial artifacts from a low call-budget
   run. Describe tested deduplication and startup interruption, then the pending leases, Redis,
   collaborative board and hybrid evidence chain.

Backup: retain completed demo runs in the local SQLite database; Run history reopens them. A fresh
checkout can regenerate all three locally. `scripts/evaluate.py` produces a portable JSON backup
of measurements. There is no bundled fictional transcript pretending to be a live execution.

Do not present the initial increment as the complete five-pattern leadership demonstration. The
final hybrid earnings-event story requires Phase 2/3 implementation and separate acceptance tests.
