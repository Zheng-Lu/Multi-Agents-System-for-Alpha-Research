# Model and architecture comparisons

Coordination, role, provider/model, task, dataset and execution budget are separate inputs.
The run request persists all of them, and invocation records retain requested/served/original model
identities. The UI table shows descriptive measurements, default and overridden assignments, cost
budgets and outcomes. It does not calculate causal superiority or hide heterogeneous assignments.

Architecture experiment: hold models, tool permissions, task, snapshot, limits and evaluation criteria
fixed; vary coordination. Model experiment: hold architecture and other inputs fixed; vary models.
Mixed-team optimization: explicitly vary role assignments under a common total budget. Report
fallback-enabled experiments separately; a fallback changes model identity and may move data only
when explicitly authorized.

The controlled-v1 slice uses two frozen workloads and four variants (including the single-context
parallel-tools control). Its Demo-only group endpoint fixes MockProvider and identical aggregate
budgets. Serial variant execution prevents cross-run timing contention. Review decisions, proposals
and publication grading are separate measurements; no model win is inferred from a metric sort.
This is a mechanics comparison, not a model benchmark. See evaluation.md for metric definitions.

The legacy `scripts/evaluate.py --case legacy` runs the three available architectures under a common MockProvider
and repeated fixed task. It checks research-process outcomes and records calls, tools, usage
approximations and local latency. Generator–Verifier additionally includes its mechanism-specific
invalid candidate. Coverage and added work differ; this is not a controlled estimate of quality gains.

Future live experiment matrix: baseline with the lead's model; homogeneous MAS; heterogeneous MAS;
different generator/verifier models; equal-cost economical teams; configurable OpenAI/Anthropic
reference models. Record endpoint, pricing date/currency, cached/reasoning usage, retries, uncertainty,
quality gates, partial outcomes and budget exhaustion. Repeat runs and report distributions, not
single-run anecdotes. Predefine criteria before examining test outcomes. Quality/cost curves,
equal-budget optimization and statistical controls are not implemented yet.
