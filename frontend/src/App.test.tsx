import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
vi.mock('./Graph', () => ({ Graph: () => <div>Execution graph</div> }));
afterEach(() => vi.restoreAllMocks());
it('starts a credential-free run with explicit model configuration', async () => {
  const calls: { url: string; body?: string }[] = [];
  vi.stubGlobal(
    'EventSource',
    class {
      onmessage = null;
      onerror = null;
      addEventListener() {}
      close() {}
    },
  );
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body as string | undefined });
      const response = url.endsWith('/patterns')
        ? [
            {
              id: 'generator_verifier',
              name: 'Generator–Verifier',
              available: true,
              mechanism: 'Independent verification',
            },
          ]
        : url.endsWith('/models')
          ? [
              {
                provider: 'mock',
                model: 'deterministic-v1',
                smoke_tested: true,
                capabilities: { tool_calling: true },
                notes: 'Simulated',
                pricing: null,
              },
            ]
          : init?.method === 'POST'
            ? {
                run_id: 'run',
                status: 'queued',
                request: {
                  pattern: 'generator_verifier',
                  mode: 'demo',
                  models: { default: { provider: 'mock', model: 'deterministic-v1' }, roles: {} },
                },
                metrics: {
                  model_calls: 0,
                  tool_calls: 0,
                  input_tokens: 0,
                  output_tokens: 0,
                  cost_complete: false,
                  latency_ms: 0,
                },
              }
            : [];
      return { ok: true, json: async () => response };
    }),
  );
  render(<App />);
  await screen.findByRole('option', { name: 'Generator–Verifier' });
  expect(screen.getByText(/Model decisions are simulated/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Run experiment/ }));
  await waitFor(() => expect(calls.some((c) => c.url === '/api/runs' && c.body)).toBe(true));
  const request = JSON.parse(calls.find((c) => c.url === '/api/runs' && c.body)!.body!);
  expect(request.mode).toBe('demo');
  expect(request.models.default.provider).toBe('mock');
  expect(request.budget.max_cost_usd).toBe(0.1);
});
