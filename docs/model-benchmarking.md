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

The initial `scripts/evaluate.py` runs the three available architectures under a common MockProvider
and repeated fixed task. It checks research-process outcomes and records calls, tools, usage
approximations and local latency. Generator–Verifier additionally includes its mechanism-specific
invalid candidate. Coverage and added work differ; this is not a controlled estimate of quality gains.

Future live experiment matrix: baseline with the lead's model; homogeneous MAS; heterogeneous MAS;
different generator/verifier models; equal-cost economical teams; configurable OpenAI/Anthropic
reference models. Record endpoint, pricing date/currency, cached/reasoning usage, retries, uncertainty,
quality gates, partial outcomes and budget exhaustion. Repeat runs and report distributions, not
single-run anecdotes. Predefine criteria before examining test outcomes. Quality/cost curves,
equal-budget optimization and statistical controls are not implemented yet.
