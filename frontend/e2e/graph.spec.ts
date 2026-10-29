import { test, expect } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';
import type { Trace } from '../src/types';

async function startDemo(page: Page) {
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/runs') && r.request().method() === 'POST'),
    page.getByRole('button', { name: /Run experiment/ }).click(),
  ]);
  return (await response.json()).run_id as string;
}
async function position(node: Locator) {
  return node.evaluate((element) => (element as HTMLElement).style.transform);
}
async function drag(page: Page, node: Locator, dx: number, dy: number) {
  await expect(node).toBeVisible();
  const box = await node.boundingBox();
  if (!box) throw new Error('Graph node has no bounds');
  const x = box.x + box.width / 2,
    y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 12 });
  await page.mouse.up();
}

test('agents and tools can be rearranged, saved per run, simplified and reset', async ({
  page,
}) => {
  await page.goto('/');
  const runId = await startDemo(page);
  await expect(page.locator('.run-status')).toHaveText('completed');
  const generator = page.locator('.react-flow__node[data-id="generator"]');
  const backtest = page.locator('.react-flow__node[data-id="tool:run_backtest"]');
  await expect(generator).toBeVisible();
  const initial = await position(generator);
  await drag(page, generator, 75, 50);
  await expect.poll(() => position(generator)).not.toBe(initial);
  const moved = await position(generator);
  const toolInitial = await position(backtest);
  await drag(page, backtest, -60, 45);
  await expect.poll(() => position(backtest)).not.toBe(toolInitial);
  const toolMoved = await position(backtest);
  await expect(page.getByText('Layout saved for this run in this browser')).toBeVisible();
  await expect(page.locator('.react-flow__minimap')).toBeVisible();

  // Hiding research tools removes their links as well; their saved positions survive.
  await page.getByLabel('Show tools', { exact: true }).uncheck();
  await expect(page.locator('.react-flow__node.tool-node')).toHaveCount(0);
  await page.getByLabel('Show tools', { exact: true }).check();
  await expect.poll(() => position(backtest)).toBe(toolMoved);
  await page.getByLabel('Edge labels', { exact: true }).uncheck();
  await expect(page.locator('.react-flow__edge-text')).toHaveCount(0);
  await page.getByLabel('Edge labels', { exact: true }).check();

  await page.getByRole('button', { name: 'Research report', exact: true }).click();
  await page.getByRole('button', { name: 'Architecture', exact: true }).click();
  await expect.poll(() => position(generator)).toBe(moved);
  await expect.poll(() => position(backtest)).toBe(toolMoved);
  await page.reload();
  await page.getByLabel('Run history').selectOption(runId);
  await expect.poll(() => position(generator)).toBe(moved);

  await page.getByRole('button', { name: 'Expand graph', exact: true }).click();
  await expect(page.locator('.graph.graph-expanded')).toBeVisible();
  await page.getByRole('button', { name: 'Fit graph', exact: true }).click();
  await generator.click();
  await expect(page.getByRole('button', { name: 'Clear highlight' })).toBeVisible();
  await expect(page.locator('.inspect')).toContainText('Generate and revise a candidate');
  await page.getByRole('button', { name: 'Clear highlight' }).click();
  await page.screenshot({ path: '../docs/graph-controls.png', fullPage: true });

  await page.getByRole('button', { name: 'Auto arrange', exact: true }).click();
  await expect.poll(() => position(generator)).toBe(initial);
  expect(
    await page.evaluate((id) => localStorage.getItem(`alpha-mas:graph-layout:v1:${id}`), runId),
  ).toBeNull();
  const another = await startDemo(page);
  expect(another).not.toBe(runId);
  await expect(page.locator('.run-status')).toHaveText('completed');
  await expect.poll(() => position(generator)).toBe(initial);
});

test('dragging during streamed execution survives new events, new nodes and replay', async ({
  page,
}) => {
  // Deliver genuine backend events in controlled batches so we can drag before late nodes arrive.
  await page.addInitScript(() => {
    const streams: DemoStream[] = [];
    class DemoStream {
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror = null;
      done = () => {};
      constructor() {
        streams.push(this);
      }
      addEventListener(type: string, handler: () => void) {
        if (type === 'done') this.done = handler;
      }
      close() {}
    }
    Object.defineProperty(window, 'EventSource', { value: DemoStream });
    (window as unknown as { deliver: (events: unknown[], done: boolean) => void }).deliver = (
      events,
      done,
    ) => {
      const stream = streams.at(-1);
      if (!stream) throw new Error('Execution stream is not connected');
      for (const event of events) stream.onmessage?.({ data: JSON.stringify(event) });
      if (done) stream.done();
    };
  });
  await page.goto('/');
  const runId = await startDemo(page);
  await expect
    .poll(async () => (await (await page.request.get(`/api/runs/${runId}`)).json()).status)
    .toBe('completed');
  const events = (await (await page.request.get(`/api/runs/${runId}/events`)).json()) as Trace[];
  const boundary = events.findIndex((e) => e.event_type === 'handoff.candidate') + 1;
  expect(boundary).toBeGreaterThan(0);
  await page.evaluate(
    (data) =>
      (window as unknown as { deliver: (events: unknown[], done: boolean) => void }).deliver(
        data,
        false,
      ),
    events.slice(0, boundary),
  );
  const generator = page.locator('.react-flow__node[data-id="generator"]');
  await expect(generator).toBeVisible();
  const initial = await position(generator);
  await drag(page, generator, 80, 50);
  await expect.poll(() => position(generator)).not.toBe(initial);
  const moved = await position(generator);
  const viewport = await page.locator('.react-flow__viewport').getAttribute('style');

  await page.evaluate(
    (data) =>
      (window as unknown as { deliver: (events: unknown[], done: boolean) => void }).deliver(
        data,
        true,
      ),
    events.slice(boundary),
  );
  await expect(page.locator('.run-status')).toHaveText('completed');
  await expect(page.locator('.react-flow__node[data-id="lead"]')).toBeAttached();
  await expect.poll(() => position(generator)).toBe(moved);
  await expect(page.locator('.react-flow__viewport')).toHaveAttribute('style', viewport!);
  await expect(generator).toContainText('COMPLETED');

  await page.getByRole('button', { name: /Replay trace/ }).click();
  await expect(generator).toBeVisible();
  await expect.poll(() => position(generator)).toBe(moved);
});

test('graph controls remain usable on a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await startDemo(page);
  await expect(page.locator('.run-status')).toHaveText('completed');
  await page.getByLabel('Show tools', { exact: true }).uncheck();
  await expect(page.locator('.react-flow__node.tool-node')).toHaveCount(0);
  await page.getByRole('button', { name: 'Expand graph', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Collapse graph', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.locator('.react-flow__minimap')).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
