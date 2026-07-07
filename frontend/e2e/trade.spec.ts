import { expect, test } from '@playwright/test';

/**
 * Smoke test against the live stack: the matching-engine terminal loads, streams a live book from
 * the exchange, and a market order fills against resting liquidity.
 */
test('exchange terminal streams a live book and fills a market order', async ({ page }) => {
  // The root is now the project hub; the matching engine is its own app.
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Matching Engine' })).toBeVisible();
  await page.getByRole('link', { name: /Matching Engine/i }).click();

  await expect(page.getByRole('heading', { name: /Matching Engine/i })).toBeVisible();

  // The book streams in over the WebSocket — the Order Book panel populates with levels.
  await expect(page.getByRole('heading', { name: 'Order Book' })).toBeVisible();
  await expect(page.locator('.xt-row').first()).toBeVisible({ timeout: 10_000 });

  // Place a market buy — it crosses the spread and fills against resting liquidity.
  await page.getByRole('button', { name: 'Type' }).count().catch(() => {});
  await page.locator('.xt-entry select').selectOption('MARKET');
  await page.getByRole('button', { name: /BUY MARKET/i }).click();
  await expect(page.locator('.xt-result')).toContainText(/Filled/i, { timeout: 10_000 });
});
