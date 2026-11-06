import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Compare } from './Compare';
import type { Budget, CasePreset, Comparison, Run } from './types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('submits fixed demo controls and keeps failures and unknown costs visible', async () => {
  const budget: Budget = {
    max_cost_usd: 0.02,
    max_calls_per_run: 1,
    max_tokens_per_run: 200000,
    max_calls_per_agent: 40,
    max_tokens_per_agent: 48000,
    max_steps: 80,
    max_runtime_seconds: 120,
    max_retries: 1,
  };
  const challenge: CasePreset = {
    case_id: 'independent-work-v1',
    name: 'Independent work',
    prompt: 'Compare evidence',
    candidates: ['momentum', 'earnings', 'sentiment'],
    description: 'Shared controls',
  };
  const run: Run = {
    run_id: 'r0',
    status: 'budget_exceeded',
    error: 'Maximum model calls per run reached',
    request: {
      pattern: 'baseline',
      mode: 'demo',
      models: { default: { provider: 'mock', model: 'deterministic-v1' }, roles: {} },
      budget,
    },
    metrics: {
      model_calls: 1,
      tool_calls: 1,
      input_tokens: 100,
      output_tokens: 50,
      estimated_cost_usd: null,
      cost_complete: false,
      latency_ms: 30,
      coordination_events: 0,
      peak_input_tokens: null,
      usage_complete: false,
    },
  };
  const group: Comparison = {
    comparison_id: 'group',
    case_id: challenge.case_id,
    created_at: '2026-11-06T12:00:00Z',
    status: 'finished',
    request: { budget, simulated_latency_ms: 0 },
    case: challenge,
    run_ids: ['r0', 'r1', 'r2', 'r3'],
    takeaways: ['Incomplete variants prevent a complete architecture comparison.'],
    rows: ['Sequential', 'Parallel tools', 'Generator–Verifier', 'Orchestrator–Subagent'].map(
      (label, i) => ({
        label,
        run: { ...run, run_id: `r${i}` },
        evidence_coverage: 0,
        review_caught_issue: null,
        repair_completed: null,
        top_proposed_validity: 'unknown',
        published_count: null,
        blocked_count: null,
      }),
    ),
  };
  const posted: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init?: RequestInit) => {
      if (init?.body) posted.push(JSON.parse(init.body as string));
      return { ok: true, json: async () => (init?.body ? group : []) };
    }),
  );
  const onOpen = vi.fn(async () => {});
  render(<Compare cases={[challenge]} budget={budget} onOpen={onOpen} onFinished={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: 'Run controlled demo (4 variants)' }));
  const table = await screen.findByTestId('comparison-scorecard');
  expect(posted).toEqual([{ case_id: challenge.case_id, budget, simulated_latency_ms: 0 }]);
  expect(within(table).getAllByText('budget exceeded')).toHaveLength(4);
  expect(
    within(within(table).getByRole('row', { name: /^Estimated API cost/ })).getAllByText('Unknown'),
  ).toHaveLength(4);
  expect(screen.getByText(/Incomplete variants prevent/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Inspect run r2' }));
  await waitFor(() => expect(onOpen).toHaveBeenCalledWith('r2'));
});
