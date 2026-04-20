import { expect, test } from '@playwright/test'

test('admin page renders and attempts backend health check', async ({ page }) => {
  await page.route('**/health', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' }),
  )

  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1, name: /admin/i })).toBeVisible()
  await expect(page.getByTestId('health-status')).toHaveText('ok')
})
