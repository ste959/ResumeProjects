import { expect, test } from '@playwright/test';

/**
 * End-to-end happy path against the live stack: a trader stages a bond order, releases
 * and routes it, and the matching engine fills it — all through the real UI and API.
 */
test('stage → route → fill a market order', async ({ page }) => {
  await page.goto('/');

  // Order ticket: pick a liquid treasury, market order, and stage it.
  await expect(page.getByRole('heading', { name: 'Order Ticket' })).toBeVisible();
  await page.getByLabel('Security').selectOption('912828YK0');
  await page.getByRole('button', { name: /Stage BUY Order/i }).click();

  // Confirmation banner appears.
  await expect(page.getByText(/staged \(/i)).toBeVisible();

  // The new order is the top row of the blotter. Release then route it.
  const firstRow = page.locator('.blotter tbody tr').first();
  await firstRow.getByRole('button', { name: 'Stage', exact: true }).click();
  await firstRow.getByRole('button', { name: 'Route', exact: true }).click();

  // The CLOB fills the market order → the row shows a (partially) filled state.
  await expect(firstRow.getByText(/FILLED/)).toBeVisible();
});
