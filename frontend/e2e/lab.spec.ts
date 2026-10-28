import { test, expect } from '@playwright/test';
test('verification, evidence inspection and persisted trace replay', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'See coordination happen.' })).toBeVisible();
  await page.getByRole('button', { name: /Run experiment/ }).click();
  await expect(page.locator('.run-status')).toHaveText('completed');
  await page.getByRole('button', { name: 'Research report', exact: true }).click();
  await expect(page.getByText('Attempt 1:')).toContainText('rejected');
  await expect(page.getByText('Attempt 2:')).toContainText('accepted');
  await expect(page.getByText('LEAK · excluded')).toBeVisible();
  await page.getByRole('button', { name: /Replay trace/ }).click();
  await expect(page.getByText(/REPLAY ·/)).toBeVisible();
  await page.getByRole('button', { name: 'Evidence & trace', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Computed findings' })).toBeVisible();
  await page.reload();
  await page.getByLabel('Run history').selectOption({ index: 1 });
  await expect(page.locator('.run-status')).toHaveText('completed');
  await page.screenshot({ path: '../docs/lab-screenshot.png', fullPage: true });
});
test('orchestrator exposes independent worker nodes', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Coordination pattern').selectOption('orchestrator_subagent');
  await page.getByRole('button', { name: /Run experiment/ }).click();
  await expect(page.locator('.run-status')).toHaveText('completed');
  await expect(page.locator('.react-flow__node:not(.tool-node)')).toHaveCount(4);
  await page.locator('.react-flow__node').filter({ hasText: 'earnings researcher' }).click();
  await expect(page.locator('.inspect')).toContainText('Evaluate only earnings');
});
