# Pattern mapping

Authoritative definitions: [Anthropic, Multi-agent coordination patterns](https://claude.com/resources/articles/multi-agent-coordination-patterns),
read 2026-10-28. The following definition summaries follow that article; the research roles,
verification gates, SQLite keys and lifetime enforcement are our implementation choices.

| Pattern | Definition summary | Current mapping |
|---|---|---|
| Generator–Verifier | Generate, independently evaluate, return specific feedback, revise until accepted or bounded termination. | `patterns/generator_verifier.py`; two private contexts; candidate evidence and feedback handoffs; deterministic gate; leaking → corrected factor demo; rejection/acceptance and exhaustion tests. |
| Orchestrator–Subagent | Lead decomposes work, delegates bounded tasks to isolated workers, synthesizes their returned findings; workers end after assignment. | `patterns/orchestrator_subagent.py`; tool-submitted decomposition; TaskGroup workers; scoped contexts; evidence-only synthesis; tested distinct contexts and three returned findings. |
| Agent Teams | Persistent autonomous teammates claim queued assignments and retain useful context across them. | Pending. Need durable identities, context, leases, heartbeat, restart and two-assignment demonstration. |
| Message Bus | Agents publish events and subscribe by topic; routing triggers independent reactions. | Pending. Need Redis Streams subscriptions, consumer groups, correlation, acknowledgments, retries, replay and deduplicated outcomes. SSE traces are observation, not this mechanism. |
| Shared State | Agents directly read and update shared knowledge, discovering and building on others' findings. | Pending. Need versioned Evidence Board, optimistic concurrency, direct discovery, provenance and bounded convergence. Persisted findings alone do not qualify. |

Baseline is our experimental control, not one of the official five. Hybrid will be our composition,
not a sixth official pattern. Agent lifetime boundaries are enforced by session ownership; live
workers currently run as asyncio tasks within one process, not independently deployable processes.

Current state owners: Session owns conversation context; Runtime owns run lifecycle; ModelRouter
owns allowances and assignment resolution; SQLite owns durable evidence and traces. Temporary
workers cannot read one another's conversations. Generator and verifier retain only their own
contexts; the verifier receives the candidate, never the generator transcript.

Acceptance tests live in `backend/tests/test_runtime_api.py`. API/persistence/provider boundaries
are separately tested. Failures terminate a run with partial artifacts; revision exhaustion is a
completed research execution whose candidate is rejected, not a falsely accepted candidate.

Controlled workloads are additional lab experiments, not official pattern definitions. Their
Generator–Verifier path uses separate researcher/reviewer sessions, evidence-based model reviews,
feedback and bounded repairs. Baseline uses the same tools and one session for self-review; its
parallel-tools variant concurrently executes validated calls without starting other agent contexts.
Orchestrator workers independently research and self-review their assigned candidates before
returning findings/reviews to the lead. All variants submit proposals before a common publication
gate grades versions. Recheck of the official source on 2026-11-04 retained these lifetime and
communication boundaries. Coverage: test_comparison.py and test_comparison_api.py.

Supplementary sources consulted:

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents): prefer simple composable mechanisms and explicit tool interfaces.
- [When to use multi-agent systems](https://claude.com/resources/articles/building-multi-agent-systems-when-and-how-to-use-them): isolated contexts and coordination costs.
- [Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system): scoped delegation and synthesis.
- [Context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents): select relevant context and retain concise evidence.
- [When to fold subagents into the main loop](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop): retain the baseline and measure whether extra agents help.

No contradiction with the five names was found. Durable teams, Redis and concurrency details in
this lab are engineering acceptance requirements, not additional official Anthropic patterns.
