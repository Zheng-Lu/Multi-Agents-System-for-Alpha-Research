import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from './api';
import type { Budget, CasePreset, Comparison, ComparisonRow } from './types';

export function Compare({
  cases,
  budget,
  onOpen,
  onFinished,
}: {
  cases: CasePreset[];
  budget: Budget;
  onOpen: (id: string) => Promise<void>;
  onFinished: () => void;
}) {
  const [groups, setGroups] = useState<Comparison[]>([]);
  const [group, setGroup] = useState<Comparison | null>(null);
  const [caseId, setCaseId] = useState('independent-work-v1');
  const [delay, setDelay] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const running = group?.status === 'running';
  const comparisonId = group?.comparison_id;

  useEffect(() => {
    let disposed = false;
    api<Comparison[]>('/evaluations')
      .then((items) => {
        if (!disposed) {
          setGroups(items);
          setGroup(items[0] ?? null);
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!comparisonId || !running) return;
    let disposed = false;
    let polling = false;
    const timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const next = await api<Comparison>(`/evaluations/${comparisonId}`);
        if (!disposed) {
          setGroup(next);
          setGroups((old) =>
            old.map((item) => (item.comparison_id === next.comparison_id ? next : item)),
          );
          if (next.status === 'finished') onFinished();
        }
      } catch (e) {
        if (!disposed) setError((e as Error).message);
      } finally {
        polling = false;
      }
    }, 500);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [comparisonId, running, onFinished]);

  async function start() {
    setBusy(true);
    setError('');
    try {
      const next = await api<Comparison>('/evaluations/compare', {
        case_id: caseId,
        budget,
        simulated_latency_ms: delay,
      });
      setGroup(next);
      setGroups((old) => [next, ...old]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!group) return;
    setBusy(true);
    try {
      await Promise.all(group.run_ids.map((id) => api(`/runs/${id}/cancel`, {})));
      setGroup(await api<Comparison>(`/evaluations/${group.comparison_id}`));
      onFinished();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const metrics: [string, (row: ComparisonRow) => ReactNode][] = [
    [
      'Execution outcome',
      (r) => (
        <span className={`run-status ${r.run.status}`}>{r.run.status.replaceAll('_', ' ')}</span>
      ),
    ],
    [
      'Reviewer caught injected issue',
      (r) =>
        r.review_caught_issue === null
          ? 'Not applicable / not observed'
          : r.review_caught_issue
            ? 'Yes'
            : 'No',
    ],
    [
      'Repair completed',
      (r) => (r.repair_completed === null ? 'Unknown' : r.repair_completed ? 'Yes' : 'No'),
    ],
    [
      'Top agent proposal validity',
      (r) => (
        <span className={`publication ${r.top_proposed_validity}`}>
          {r.top_proposed_validity.replaceAll('_', ' ')}
        </span>
      ),
    ],
    [
      'Published / blocked recommendations',
      (r) => (r.published_count === null ? 'Unknown' : `${r.published_count} / ${r.blocked_count}`),
    ],
    ['Research evidence coverage', (r) => `${(r.evidence_coverage * 100).toFixed(0)}%`],
    [
      'Model calls / tool calls',
      (r) => `${r.run.metrics.model_calls} / ${r.run.metrics.tool_calls}`,
    ],
    [
      'Tokens · demo estimate',
      (r) =>
        `${r.run.metrics.input_tokens + r.run.metrics.output_tokens}${r.run.metrics.usage_complete ? '' : ' · incomplete'}`,
    ],
    ['Peak input tokens · demo estimate', (r) => r.run.metrics.peak_input_tokens ?? 'Unknown'],
    [
      'Estimated API cost · demo',
      (r) =>
        r.run.metrics.cost_complete
          ? `$${r.run.metrics.estimated_cost_usd?.toFixed(5)}`
          : 'Unknown',
    ],
    [
      'Wall time · local / includes configured delay',
      (r) => `${(r.run.metrics.latency_ms / 1000).toFixed(2)}s`,
    ],
    ['Coordination events', (r) => r.run.metrics.coordination_events],
  ];

  return (
    <section className="panel compare-panel">
      <div className="eyebrow">CONTROLLED ARCHITECTURE COMPARISON</div>
      <h2>Same task. Visible trade-offs.</h2>
      <p>
        Compare three architectures and a Single-Agent parallel-tools control. Variants run one at a
        time; tools and workers within each variant can execute concurrently.
      </p>
      <div className="comparison-controls">
        <label>
          Challenge preset
          <select
            aria-label="Comparison challenge"
            value={caseId}
            disabled={busy || running}
            onChange={(e) => setCaseId(e.target.value)}
          >
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {c.name} · {c.case_id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Simulated delay per model call
          <select
            aria-label="Simulated comparison delay"
            value={delay}
            disabled={busy || running}
            onChange={(e) => setDelay(Number(e.target.value))}
          >
            <option value={0}>0 ms · zero-delay control</option>
            <option value={100}>100 ms · simulated</option>
            <option value={250}>250 ms · simulated</option>
          </select>
        </label>
        <button className="primary" disabled={busy || running || !cases.length} onClick={start}>
          Run controlled demo (4 variants)
        </button>
        {running && (
          <button disabled={busy} onClick={cancel}>
            Cancel comparison
          </button>
        )}
      </div>
      <p className="mode-note">
        DEMO · SYNTHETIC DATA · Scripted model decisions in every role. These runs measure execution
        mechanics. Live model quality and API cost advantages require separately authorized
        experiments.
      </p>
      <p className="muted">
        New groups use the execution budget from the sidebar. All four receive the same aggregate
        allowance. The one-click comparison always uses MockProvider, regardless of the model
        selected for individual runs.
      </p>
      {error && (
        <div role="alert" className="alert">
          {error}
        </div>
      )}
      {!!groups.length && (
        <label>
          Saved comparison
          <select
            aria-label="Saved comparison"
            value={group?.comparison_id ?? ''}
            onChange={(e) =>
              setGroup(groups.find((g) => g.comparison_id === e.target.value) ?? null)
            }
          >
            {groups.map((g) => (
              <option key={g.comparison_id} value={g.comparison_id}>
                {g.case.name} · {g.created_at.slice(0, 19)} · {g.comparison_id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      )}
      {group && (
        <>
          <h3>
            {group.case.name} <small>{group.status}</small>
          </h3>
          <p>{group.case.description}</p>
          <div className="comparison-controls-summary">
            <strong>Frozen controls · {group.case_id}</strong>
            <p>
              Candidates: {group.case.candidates.join(', ')} · synthetic-v1{' '}
              {group.case_id === 'review-repair-v1' && '+ earnings-revisions-v1'}
            </p>
            <p>
              Every role: mock/deterministic-v1 · {group.request.simulated_latency_ms} ms simulated
              delay / call.
            </p>
            <p>
              Per variant: {group.request.budget.max_calls_per_run} calls /{' '}
              {group.request.budget.max_tokens_per_run.toLocaleString()} aggregate tokens;{' '}
              {group.request.budget.max_calls_per_agent} calls /{' '}
              {group.request.budget.max_tokens_per_agent.toLocaleString()} tokens per agent; $
              {group.request.budget.max_cost_usd} estimated cost limit.
            </p>
            <details>
              <summary>Task and complete execution budgets</summary>
              <p>{group.case.prompt}</p>
              <pre>{JSON.stringify(group.request, null, 2)}</pre>
            </details>
          </div>
          <div className="table-scroll">
            <table className="scorecard" data-testid="comparison-scorecard">
              <thead>
                <tr>
                  <th>Measured outcome</th>
                  {group.rows.map((r) => (
                    <th key={r.run.run_id}>
                      {r.label}
                      <button onClick={() => onOpen(r.run.run_id)}>
                        Inspect run {r.run.run_id.slice(0, 8)}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map(([name, render]) => (
                  <tr key={name}>
                    <th scope="row">{name}</th>
                    {group.rows.map((r) => (
                      <td key={r.run.run_id}>
                        {render(r)}
                        {name === 'Execution outcome' && r.run.error && (
                          <small className="rejected">{r.run.error}</small>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="comparison-takeaways">
            <h3>Observed results</h3>
            <ul>
              {group.takeaways.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </div>
          <p className="muted">
            Use a single agent for compact work; parallel tools can handle independent calculations
            in one context. Scoped subagents isolate investigations. Independent verification adds a
            separate review boundary. These are mechanism choices; the scorecard does not assume a
            winner.
          </p>
        </>
      )}
    </section>
  );
}
