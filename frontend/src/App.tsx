import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { Graph } from './Graph';
import type {
  Artifact,
  Assignments,
  Finding,
  ModelConfig,
  ModelEntry,
  Pattern,
  Report,
  Run,
  Trace,
} from './types';

const mock: ModelConfig = { provider: 'mock', model: 'deterministic-v1' };
const roles = [
  'lead',
  'generator',
  'verifier',
  'momentum_researcher',
  'earnings_researcher',
  'sentiment_researcher',
];
const terminal = [
  'completed',
  'failed',
  'cancelled',
  'budget_exceeded',
  'timed_out',
  'interrupted',
];
const pct = (n: number) => `${(n * 100).toFixed(2)}%`;
const key = (m: ModelConfig) => `${m.provider}/${m.model}`;

export default function App() {
  const [patterns, setPatterns] = useState<Pattern[]>([]),
    [models, setModels] = useState<ModelEntry[]>([]);
  const [pattern, setPattern] = useState('generator_verifier'),
    [mode, setMode] = useState('demo');
  const [prompt, setPrompt] = useState(
    'Evaluate momentum, earnings and news signals for 5-day returns. Identify leakage and compare cost-adjusted evidence.',
  );
  const [assignments, setAssignments] = useState<Assignments>({ default: mock, roles: {} });
  const [saved, setSaved] = useState<{ name: string; models: Assignments }[]>([]),
    [configName, setConfigName] = useState('My research team');
  const [run, setRun] = useState<Run | null>(null),
    [history, setHistory] = useState<Run[]>([]);
  const [events, setEvents] = useState<Trace[]>([]),
    [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState('Architecture');
  const [selected, setSelected] = useState<string | null>(null),
    [showModels, setShowModels] = useState(false);
  const [cost, setCost] = useState(0.1),
    [tokens, setTokens] = useState(48000),
    [calls, setCalls] = useState(10),
    [steps, setSteps] = useState(80),
    [seconds, setSeconds] = useState(120);
  const [replaying, setReplaying] = useState(false),
    [replayIndex, setReplayIndex] = useState(0);
  const source = useRef<EventSource | null>(null);
  const visible = replaying ? events.slice(0, replayIndex) : events;
  const report = artifacts.find((a) => a.kind === 'report')?.payload as unknown as
    Report | undefined;
  const findings = artifacts
    .filter((a) => a.kind === 'finding')
    .map((a) => a.payload as unknown as Finding);
  const active = !!run && !terminal.includes(run.status);

  useEffect(() => {
    Promise.all([
      api<Pattern[]>('/patterns'),
      api<ModelEntry[]>('/models'),
      api<Run[]>('/runs'),
      api<{ name: string; models: Assignments }[]>('/model-configurations'),
    ])
      .then(([p, m, h, s]) => {
        setPatterns(p);
        setModels(m);
        setHistory(h);
        setSaved(s);
      })
      .catch((e) => setError(e.message));
    return () => source.current?.close();
  }, []);
  useEffect(() => {
    if (!replaying) return;
    const timer = setInterval(() => setReplayIndex((i) => Math.min(i + 1, events.length)), 100);
    return () => clearInterval(timer);
  }, [replaying, events.length]);

  async function refresh(id: string) {
    const [r, a, h] = await Promise.all([
      api<Run>(`/runs/${id}`),
      api<Artifact[]>(`/runs/${id}/artifacts`),
      api<Run[]>('/runs'),
    ]);
    setRun(r);
    setArtifacts(a);
    setHistory(h);
  }
  function subscribe(id: string) {
    source.current?.close();
    const stream = new EventSource(`/api/runs/${id}/stream`);
    source.current = stream;
    stream.onmessage = (event) => {
      const item: Trace = JSON.parse(event.data);
      setEvents((old) => (old.some((e) => e.event_id === item.event_id) ? old : [...old, item]));
    };
    stream.addEventListener('done', () => {
      stream.close();
      refresh(id).catch((e) => setError(e.message));
    });
    stream.onerror = () => {
      setError('Execution stream disconnected. Reopen this run to replay persisted events.');
      stream.close();
      refresh(id).catch((e) => setError(e.message));
    };
  }
  async function start() {
    setBusy(true);
    setError('');
    setReplaying(false);
    setEvents([]);
    setArtifacts([]);
    setSelected(null);
    try {
      const r = await api<Run>('/runs', {
        pattern,
        mode,
        task: { prompt },
        models: assignments,
        budget: {
          max_cost_usd: cost,
          max_tokens_per_agent: tokens,
          max_calls_per_agent: calls,
          max_steps: steps,
          max_runtime_seconds: seconds,
          max_retries: 1,
        },
        max_revisions: 2,
        inject_leak: true,
      });
      setRun(r);
      subscribe(r.run_id);
      setTab('Architecture');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openRun(id: string) {
    source.current?.close();
    setReplaying(false);
    setSelected(null);
    setError('');
    try {
      await refresh(id);
      setEvents(await api<Trace[]>(`/runs/${id}/events`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function choose(value: string): ModelConfig {
    const m = models.find((m) => key(m) === value);
    return m ? { provider: m.provider, model: m.model } : mock;
  }
  function preset(name: string) {
    if (name === 'demo') {
      setMode('demo');
      setAssignments({ default: mock, roles: {} });
      return;
    }
    setMode('live');
    const glm = models.find((m) => m.provider === 'glm') ?? mock;
    if (name === 'economical')
      setAssignments({ default: { provider: glm.provider, model: glm.model }, roles: {} });
    if (name === 'mixed')
      setAssignments({
        default: { provider: glm.provider, model: glm.model },
        roles: Object.fromEntries(
          [
            ['verifier', 'deepseek'],
            ['earnings_researcher', 'qwen'],
            ['sentiment_researcher', 'kimi'],
          ].map(([role, provider]) => {
            const m = models.find((m) => m.provider === provider) ?? mock;
            return [role, { provider: m.provider, model: m.model }];
          }),
        ),
      });
    if (name === 'benchmark' || name === 'openai') {
      const m = models.find((m) => m.provider === 'openai') ?? mock;
      setAssignments({ default: { provider: m.provider, model: m.model }, roles: {} });
    }
  }
  async function save() {
    try {
      await api('/model-configurations', { name: configName, models: assignments });
      setSaved(await api('/model-configurations'));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const options = models.map((m) => (
    <option key={key(m)} value={key(m)}>
      {key(m)}
      {m.provider === 'mock'
        ? ' · tested demo'
        : m.smoke_tested
          ? ' · live smoke-tested'
          : ' · live unverified'}
    </option>
  ));
  const own = visible.filter((e) => e.agent_id === selected);
  const nodeArtifacts = artifacts.filter((a) => a.agent_id === selected);
  const selectedModel = own.findLast((e) => e.model_id);
  const invocationEvents = visible.filter((e) => e.event_type === 'model.completed');
  const tokensOf = (items: Trace[], field: string) =>
    items.reduce(
      (sum, e) =>
        sum + Number((e.metadata.usage as Record<string, unknown> | undefined)?.[field] ?? 0),
      0,
    );
  const measured =
    active || replaying
      ? {
          model_calls: visible.filter((e) => e.event_type === 'model.started').length,
          tool_calls: visible.filter((e) => e.event_type === 'tool.completed').length,
          input_tokens: tokensOf(invocationEvents, 'input_tokens'),
          output_tokens: tokensOf(invocationEvents, 'output_tokens'),
          cost_complete:
            invocationEvents.every((e) => e.metadata.cost_complete) &&
            !visible.some((e) => e.event_type === 'model.failed'),
          estimated_cost_usd: invocationEvents.reduce(
            (sum, e) => sum + Number(e.metadata.estimated_cost_usd ?? 0),
            0,
          ),
          latency_ms: visible.length
            ? Date.parse(visible.at(-1)!.timestamp) - Date.parse(visible[0].timestamp)
            : 0,
        }
      : run?.metrics;

  return (
    <div className="shell">
      <header>
        <a className="brand" href="/" aria-label="Alpha Research home">
          <span className="brand-mark">α</span>
          <span>
            ALPHA RESEARCH<small>MULTI-AGENT SYSTEMS LAB</small>
          </span>
        </a>
        <div className="header-right">
          <span className="tag">SYNTHETIC DATA · v1</span>
          <span className="status-dot" />
          Local research environment
        </div>
      </header>
      <div className="workspace">
        <aside>
          <div className="eyebrow">EXPERIMENT SETUP</div>
          <h2>Coordination lab</h2>
          <p className="muted">
            One research environment.
            <br />
            Different ways to coordinate.
          </p>
          <label>
            Coordination pattern
            <select
              aria-label="Coordination pattern"
              value={pattern}
              disabled={active}
              onChange={(e) => setPattern(e.target.value)}
            >
              {patterns.map((p) => (
                <option key={p.id} value={p.id} disabled={!p.available}>
                  {p.name}
                  {!p.available ? ' · pending' : ''}
                </option>
              ))}
            </select>
          </label>
          <p className="mechanism">{patterns.find((p) => p.id === pattern)?.mechanism}</p>
          <label>
            Research task
            <textarea
              aria-label="Research task"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
            />
          </label>
          <label>
            Execution mode
            <select
              aria-label="Execution mode"
              value={mode}
              disabled={active}
              onChange={(e) => {
                setMode(e.target.value);
                if (e.target.value === 'demo') preset('demo');
              }}
            >
              <option value="demo">Deterministic demo · no credentials</option>
              <option value="live">Live · bounded paid inference</option>
            </select>
          </label>
          <div className="mode-note">
            {mode === 'demo'
              ? 'Model decisions are simulated. Tools, calculations, persistence and coordination execute locally.'
              : 'Requires server opt-in, credentials and a priced model profile. Model selectors show live verification status.'}
          </div>
          <button className="model-button" onClick={() => setShowModels(!showModels)}>
            Model assignments <span>{showModels ? '−' : '+'}</span>
            <small>{key(assignments.default)}</small>
          </button>
          {showModels && (
            <div className="model-settings">
              <label>
                Preset
                <select
                  aria-label="Model preset"
                  defaultValue=""
                  onChange={(e) => preset(e.target.value)}
                >
                  <option value="" disabled>
                    Choose preset
                  </option>
                  <option value="demo">Credential-free demo</option>
                  <option value="economical">Economical candidate · GLM</option>
                  <option value="openai">OpenAI · Standard pricing</option>
                  <option value="mixed">Mixed-provider candidate</option>
                  <option value="benchmark">High-capability candidate</option>
                </select>
              </label>
              <label>
                Global model
                <select
                  aria-label="Global model"
                  value={key(assignments.default)}
                  onChange={(e) => setAssignments({ default: choose(e.target.value), roles: {} })}
                >
                  {options}
                </select>
              </label>
              <p className="muted">Changing the global model applies it to every role.</p>
              {roles.map((role) => (
                <label key={role}>
                  {role.replaceAll('_', ' ')}
                  <select
                    aria-label={`${role} model`}
                    value={key(assignments.roles[role] ?? assignments.default)}
                    onChange={(e) =>
                      setAssignments({
                        ...assignments,
                        roles: { ...assignments.roles, [role]: choose(e.target.value) },
                      })
                    }
                  >
                    {options}
                  </select>
                </label>
              ))}
              <input
                aria-label="Configuration name"
                value={configName}
                onChange={(e) => setConfigName(e.target.value)}
              />
              <button onClick={save}>Save configuration</button>
              {saved.length > 0 && (
                <select
                  aria-label="Saved configurations"
                  defaultValue=""
                  onChange={(e) => setAssignments(saved[Number(e.target.value)].models)}
                >
                  <option value="" disabled>
                    Load saved configuration
                  </option>
                  {saved.map((s, i) => (
                    <option key={s.name} value={i}>
                      {s.name}
                    </option>
                  ))}
                </select>
              )}
              <div className="capability-list">
                {models
                  .filter((m) =>
                    Object.values({ ...assignments.roles, default: assignments.default }).some(
                      (c) => key(c) === key(m),
                    ),
                  )
                  .map((m) => (
                    <p key={key(m)}>
                      <strong>{key(m)}</strong>
                      <br />
                      Tools: {m.capabilities.tool_calling ? 'yes' : 'no'} · Schema validation:{' '}
                      {m.capabilities.structured_output ? 'yes' : 'no'}
                      <br />
                      {m.pricing
                        ? `$${m.pricing.input_per_million} in / $${m.pricing.output_per_million} out per 1M · ${m.pricing.effective_date}`
                        : 'Pricing unknown; live runs blocked.'}
                      <br />
                      {m.notes}
                    </p>
                  ))}
              </div>
            </div>
          )}
          <details>
            <summary>Execution budget</summary>
            <div className="budgets">
              <label>
                Max estimated cost ($)
                <input
                  aria-label="Max cost"
                  type="number"
                  min="0"
                  max="10"
                  step=".01"
                  value={cost}
                  onChange={(e) => setCost(Number(e.target.value))}
                />
              </label>
              <label>
                Tokens per agent
                <input
                  type="number"
                  value={tokens}
                  onChange={(e) => setTokens(Number(e.target.value))}
                />
              </label>
              <label>
                Calls per agent
                <input
                  type="number"
                  value={calls}
                  onChange={(e) => setCalls(Number(e.target.value))}
                />
              </label>
              <label>
                Execution steps
                <input
                  type="number"
                  value={steps}
                  onChange={(e) => setSteps(Number(e.target.value))}
                />
              </label>
              <label>
                Runtime (seconds)
                <input
                  type="number"
                  value={seconds}
                  onChange={(e) => setSeconds(Number(e.target.value))}
                />
              </label>
            </div>
          </details>
          <button className="primary" disabled={busy || active} onClick={start}>
            {busy ? 'Starting…' : '▶  Run experiment'}
          </button>
          <div className="sidebar-bottom">
            5 trading-day target · 8 synthetic equities
            <br />
            Research only. No trading connections.
          </div>
        </aside>
        <main>
          <div className="page-title">
            <div>
              <div className="eyebrow">ARCHITECTURE / OBSERVABILITY</div>
              <h1>See coordination happen.</h1>
              <p>Follow context boundaries, tool evidence and verification decisions.</p>
            </div>
            <span className={`run-status ${run?.status ?? ''}`}>
              {run?.status.replaceAll('_', ' ') ?? 'Ready to run'}
            </span>
          </div>
          {error && (
            <div role="alert" className="alert">
              {error}
            </div>
          )}
          {run?.error && <div className="alert">{run.error}</div>}
          <div className="metrics">
            {[
              ['Model calls', measured?.model_calls ?? '—'],
              ['Tool calls', measured?.tool_calls ?? '—'],
              ['Tokens', measured ? measured.input_tokens + measured.output_tokens : '—'],
              [
                'Estimated API cost',
                measured
                  ? measured.cost_complete
                    ? `$${measured.estimated_cost_usd?.toFixed(5)}`
                    : 'Unknown / incomplete'
                  : '—',
              ],
              ['Wall time', measured ? `${(measured.latency_ms / 1000).toFixed(2)}s` : '—'],
            ].map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <nav aria-label="Views">
            {['Architecture', 'Research report', 'Evidence & trace', 'Compare'].map((t) => (
              <button className={tab === t ? 'active' : ''} key={t} onClick={() => setTab(t)}>
                {t}
              </button>
            ))}
            <div className="nav-actions">
              <button
                disabled={!run || active}
                onClick={() => {
                  setReplaying(true);
                  setReplayIndex(0);
                  setTab('Architecture');
                }}
              >
                ↻ Replay trace
              </button>
              {active && (
                <button
                  onClick={() =>
                    api<Run>(`/runs/${run!.run_id}/cancel`, {})
                      .then(setRun)
                      .catch((e) => setError(e.message))
                  }
                >
                  Cancel run
                </button>
              )}
            </div>
          </nav>
          {tab === 'Architecture' && (
            <>
              <section className="graph-panel">
                <div className="panel-heading">
                  <div>
                    <span className="status-dot" />
                    {replaying ? `REPLAY · ${replayIndex}/${events.length}` : 'EXECUTION GRAPH'}
                  </div>
                  <span>Click an agent to inspect its context</span>
                </div>
                {visible.length ? (
                  <div className="graph">
                    <Graph events={visible} onSelect={setSelected} />
                  </div>
                ) : (
                  <div className="empty-state">
                    <div className="empty-symbol">α</div>
                    <h3>Your experiment starts here</h3>
                    <p>
                      Select a coordination pattern and run the synthetic research task.
                      <br />
                      Agents and connections appear from actual backend events.
                    </p>
                    <div className="legend">
                      <span>● Agent contexts</span>
                      <span>↗ Scoped handoffs</span>
                      <span>✓ Deterministic gates</span>
                    </div>
                  </div>
                )}
              </section>
              {selected && (
                <section className="inspect">
                  <h3>
                    {selected.replaceAll('_', ' ')}{' '}
                    <button onClick={() => setSelected(null)}>Close</button>
                  </h3>
                  <p>
                    {String(
                      own.find((e) => e.event_type === 'agent.started')?.metadata.scope ?? '',
                    )}
                  </p>
                  <p className="mono">
                    {selectedModel?.provider_id} / {selectedModel?.model_id} · {own.length} events ·{' '}
                    {nodeArtifacts.length} artifacts
                  </p>
                  <p>
                    Reported tokens:{' '}
                    {tokensOf(
                      own.filter((e) => e.event_type === 'model.completed'),
                      'input_tokens',
                    )}{' '}
                    input /{' '}
                    {tokensOf(
                      own.filter((e) => e.event_type === 'model.completed'),
                      'output_tokens',
                    )}{' '}
                    output. Tool evidence is listed below.
                  </p>
                  <p>
                    Context: <code>{String(own[0]?.metadata.context_id ?? '')}</code>. Private to
                    this agent; scoped evidence handoffs only.
                  </p>
                  <p>
                    {String(
                      own.findLast((e) => e.metadata.decision_summary)?.metadata.decision_summary ??
                        'Working…',
                    )}
                  </p>
                  <div className="tool-tags">
                    {own
                      .filter((e) => e.event_type === 'tool.completed')
                      .map((e) => (
                        <span key={e.event_id}>
                          {String(e.metadata.tool)} ↗ {e.output_ref?.slice(0, 8)}
                        </span>
                      ))}
                  </div>
                  <details>
                    <summary>Inspect persisted artifacts ({nodeArtifacts.length})</summary>
                    {nodeArtifacts.map((a) => (
                      <details key={a.artifact_id}>
                        <summary>
                          {a.kind} · {a.artifact_id.slice(0, 8)}
                        </summary>
                        <pre>{JSON.stringify(a.payload, null, 2)}</pre>
                      </details>
                    ))}
                  </details>
                </section>
              )}
              <section className="panel timeline">
                <h3>Latest execution events</h3>
                {visible
                  .slice(-8)
                  .reverse()
                  .map((e) => (
                    <div key={e.event_id}>
                      <time>{e.timestamp.slice(11, 23)}</time>
                      <span className="mono">{e.agent_id ?? 'runtime'}</span>
                      <strong>{e.event_type}</strong>
                      <small>{e.provider_id ? `${e.provider_id}/${e.model_id}` : e.status}</small>
                    </div>
                  ))}
                {!events.length && (
                  <p className="muted">Durable events will appear here as the experiment runs.</p>
                )}
              </section>
            </>
          )}
          {tab === 'Research report' && (
            <section className="panel report">
              {report ? (
                <>
                  <div className="eyebrow">COMPUTED EVIDENCE · SYNTHETIC-v1</div>
                  <h2>{report.title}</h2>
                  <p>{report.summary}</p>
                  <div className="verdict">{report.verdict}</div>
                  {report.verifications.map((v) => (
                    <p
                      key={v.attempt}
                      className={v.verdict === 'accepted' ? 'accepted' : 'rejected'}
                    >
                      Attempt {v.attempt}: <strong>{v.verdict}</strong> {v.feedback.join(' ')}
                    </p>
                  ))}
                  <Results findings={report.findings} />
                  <h3>Methodology</h3>
                  <p>{report.findings[0]?.result.methodology}</p>
                  <h3>Limitations</h3>
                  <ul>
                    {report.findings[0]?.result.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                  <p className="muted">{report.disclaimer}</p>
                </>
              ) : (
                <Empty text="A research report appears after a completed run." />
              )}
            </section>
          )}
          {tab === 'Evidence & trace' && (
            <>
              <section className="panel">
                <h2>Computed findings</h2>
                <p className="muted">
                  Initial finding artifacts. A collaborative, versioned Evidence Board is a later
                  milestone.
                </p>
                <Results findings={findings} />
              </section>
              <section className="panel">
                <h2>Event timeline</h2>
                <div className="full-timeline">
                  {events.map((e) => (
                    <details key={e.event_id}>
                      <summary>
                        <span className="mono">
                          {e.seq} · {e.agent_id ?? 'runtime'}
                        </span>{' '}
                        {e.event_type}
                      </summary>
                      <pre>{JSON.stringify(e, null, 2)}</pre>
                    </details>
                  ))}
                </div>
              </section>
            </>
          )}
          {tab === 'Compare' && (
            <section className="panel">
              <h2>Run measurements</h2>
              <p className="muted">
                Descriptive measurements. Fix model assignments, task, data and budget before
                attributing a difference to architecture. Automated controlled comparisons are
                pending.
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Architecture / mode</th>
                      <th>Models</th>
                      <th>Cost budget</th>
                      <th>Calls / tools</th>
                      <th>Tokens</th>
                      <th>Est. cost</th>
                      <th>Time</th>
                      <th>Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((r) => (
                      <tr key={r.run_id}>
                        <td>
                          <button onClick={() => openRun(r.run_id)}>{r.request.pattern}</button>
                          <small>
                            {r.request.mode} · {r.run_id.slice(0, 8)}
                          </small>
                        </td>
                        <td>
                          {key(r.request.models.default)}
                          <small>
                            {Object.entries(r.request.models.roles)
                              .map(([role, m]) => `${role}: ${key(m)}`)
                              .join('; ') || 'Homogeneous'}
                          </small>
                        </td>
                        <td>${r.request.budget.max_cost_usd}</td>
                        <td>
                          {r.metrics.model_calls} / {r.metrics.tool_calls}
                        </td>
                        <td>{r.metrics.input_tokens + r.metrics.output_tokens}</td>
                        <td>
                          {r.metrics.cost_complete
                            ? `$${r.metrics.estimated_cost_usd?.toFixed(5)}`
                            : 'Unknown'}
                        </td>
                        <td>{(r.metrics.latency_ms / 1000).toFixed(2)}s</td>
                        <td>{r.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <footer>
            <span>ALPHA MAS LAB / 0.1</span>
            <label>
              Open persisted run{' '}
              <select
                aria-label="Run history"
                value={run?.run_id ?? ''}
                onChange={(e) => openRun(e.target.value)}
              >
                <option value="" disabled>
                  Select a run
                </option>
                {history.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.request.pattern} · {r.status} · {r.run_id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            <a href="/docs" target="_blank" rel="noreferrer">
              API reference ↗
            </a>
          </footer>
        </main>
      </div>
    </div>
  );
}
function Empty({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <p>{text}</p>
    </div>
  );
}
function Results({ findings }: { findings: Finding[] }) {
  return findings.length ? (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Candidate / author</th>
            <th>Held-out IC</th>
            <th>Gross return</th>
            <th>Net return</th>
            <th>Max drawdown</th>
            <th>Integrity</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.finding_id}>
              <td>
                <strong>{f.hypothesis.factor}</strong>
                <small>{f.agent_id}</small>
              </td>
              <td>{f.result.test_ic.toFixed(4)}</td>
              <td>{pct(f.result.gross_return)}</td>
              <td>{pct(f.result.net_return)}</td>
              <td>{pct(f.result.max_drawdown)}</td>
              <td className={f.result.leakage_detected ? 'rejected' : 'accepted'}>
                {f.result.leakage_detected ? 'LEAK · excluded' : 'Temporal gate passed'}
              </td>
              <td className="mono">{f.evidence[0]?.artifact_id.slice(0, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="muted">No computed findings yet.</p>
  );
}
