import { test, expect } from '@playwright/test';

test('controlled review comparison persists, exposes repairs and replays without inference', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await page.getByLabel('Comparison challenge').selectOption('review-repair-v1');
  await expect(page.getByLabel('Simulated comparison delay')).toHaveValue('0');
  await page.getByRole('button', { name: 'Run controlled demo (4 variants)' }).click();
  const table = page.getByTestId('comparison-scorecard');
  await expect(table.getByRole('columnheader')).toHaveCount(5);
  await expect(
    table.getByRole('row', { name: /^Execution outcome/ }).locator('.run-status'),
  ).toHaveText(['completed', 'completed', 'completed', 'completed'], { timeout: 25000 });
  await expect(
    table.getByRole('row', { name: /^Reviewer caught injected issue/ }).locator('td'),
  ).toHaveText(['Yes', 'Yes', 'Yes', 'Yes']);
  await expect(table.getByRole('row', { name: /^Repair completed/ }).locator('td')).toHaveText([
    'Yes',
    'Yes',
    'Yes',
    'Yes',
  ]);
  await expect(
    table.getByRole('row', { name: /^Top agent proposal validity/ }).locator('td'),
  ).toHaveText(['verified valid', 'verified valid', 'verified valid', 'verified valid']);
  await expect(page.locator('.comparison-controls-summary')).toContainText('mock/deterministic-v1');
  await expect(
    page.getByText(/All variants reached the same top-proposal validity outcome/),
  ).toBeVisible();
  const savedId = await page.getByLabel('Saved comparison').inputValue();
  const tableSize = await table.boundingBox();
  const frameSize = await table.locator('..').boundingBox();
  expect(tableSize!.width).toBeLessThanOrEqual(frameSize!.width + 1);
  await page.screenshot({ path: '../docs/comparison-screenshot.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.body.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.reload();
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.getByLabel('Saved comparison')).toHaveValue(savedId);
  await table
    .getByRole('columnheader', { name: /Generator–Verifier/ })
    .getByRole('button')
    .click();
  await expect(page.locator('.page-title .run-status')).toHaveText('completed');
  await expect(page.locator('.graph-panel')).toBeVisible();
  const runId = await page.getByLabel('Run history').inputValue();
  const before = await (await page.request.get(`/api/runs/${runId}/model-usage`)).json();
  await page.getByRole('button', { name: 'Research report', exact: true }).click();
  await expect(page.getByRole('heading', { name: /Agent proposal/ })).toBeVisible();
  await expect(page.locator('.report .publication.known_invalid')).toHaveCount(1);
  await expect(page.locator('.report .publication.verified_valid')).toHaveCount(4);
  await expect(page.locator('.report')).toContainText('earnings_asof');
  await page.getByRole('button', { name: /Replay trace/ }).click();
  await expect(page.getByText(/REPLAY ·/)).toBeVisible();
  const after = await (await page.request.get(`/api/runs/${runId}/model-usage`)).json();
  expect(after).toHaveLength(before.length);
});

test('scorecard retains all budget-exhausted variants and labels simulated delay', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByText('Execution budget', { exact: true }).click();
  await page.getByLabel('Aggregate calls per run').fill('1');
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await page.getByLabel('Comparison challenge').selectOption('independent-work-v1');
  await page.getByLabel('Simulated comparison delay').selectOption('100');
  await page.getByRole('button', { name: 'Run controlled demo (4 variants)' }).click();
  const table = page.getByTestId('comparison-scorecard');
  await expect(
    table.getByRole('row', { name: /^Execution outcome/ }).locator('.run-status'),
  ).toHaveText(['budget exceeded', 'budget exceeded', 'budget exceeded', 'budget exceeded']);
  await expect(
    table.getByRole('row', { name: /^Top agent proposal validity/ }).locator('td'),
  ).toHaveText(['unknown', 'unknown', 'unknown', 'unknown']);
  await expect(page.getByText(/Incomplete variants prevent/)).toBeVisible();
  await expect(page.getByText(/Wall time includes 100 ms of simulated delay/)).toBeVisible();
});
