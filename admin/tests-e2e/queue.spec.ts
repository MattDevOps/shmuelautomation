import { expect, test } from '@playwright/test'

const slot = {
  id: 's1',
  property_id: 'p1',
  scheduled_for: '2030-05-08T17:00:00',
  status: 'pending',
  priority: 200,
  posted_at: null,
  created_at: '2026-05-03T00:00:00',
  property_type: 'rent',
  property_neighborhood: 'Baka',
  property_address: '12 Emek Refaim',
  property_price: '8500.00',
}

const compose = {
  text_en: 'For rent — Baka\n3.5 rooms · 80 sqm\nILS 8,500\n12 Emek Refaim',
  text_he: 'להשכרה בBaka\n3.5 חדרים · 80 מ"ר\nILS 8,500\n12 Emek Refaim',
  whatsapp_share_url: 'https://wa.me/?text=ForRentBaka',
  facebook_share_url: null,
}

const groups = [
  {
    id: 'g1',
    platform: 'whatsapp',
    audience: 'rent',
    name: 'Baka Rentals WA',
    target_url: 'https://chat.whatsapp.com/baka',
    notes: null,
    sort_order: 0,
    active: true,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
  },
  {
    id: 'g2',
    platform: 'facebook',
    audience: 'both',
    name: 'Jerusalem Real Estate',
    target_url: 'https://facebook.com/groups/jrl',
    notes: null,
    sort_order: 0,
    active: true,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
  },
]

test('queue → share modal → check off groups → mark posted', async ({ page }) => {
  // Track whether the slot has been marked posted; affects subsequent /post-queue responses.
  let posted = false

  await page.route('**/post-queue?**', async (route) => {
    await route.fulfill({ json: posted ? [] : [slot] })
  })
  await page.route('**/post-queue/s1/posted', async (route) => {
    posted = true
    await route.fulfill({ json: { ...slot, status: 'posted' } })
  })
  await page.route('**/properties/p1/compose', async (route) => {
    await route.fulfill({ json: compose })
  })
  await page.route('**/groups?**', async (route) => {
    await route.fulfill({ json: groups })
  })

  await page.goto('/queue')

  // The seeded slot shows up under Upcoming
  await expect(page.getByRole('heading', { name: /upcoming/i })).toBeVisible()
  await expect(page.getByText('Baka', { exact: true }).first()).toBeVisible()

  // Open share modal
  await page
    .getByRole('button', { name: /compose and share baka/i })
    .click()

  // Modal renders the composed text and two groups grouped by platform
  const dialog = page.getByRole('dialog', { name: /share property/i })
  await expect(dialog).toBeVisible()
  // The composed text renders inside a readonly textarea
  await expect(dialog.locator('textarea')).toHaveValue(/for rent — baka/i)
  await expect(dialog.getByText(/whatsapp groups/i)).toBeVisible()
  await expect(dialog.getByText(/facebook groups/i)).toBeVisible()

  // Tick a group as posted
  const cb = dialog.getByRole('checkbox', { name: /baka rentals wa/i })
  await cb.check()
  await expect(cb).toBeChecked()

  // Mark slot as posted — modal closes, queue empties
  await dialog.getByRole('button', { name: /mark slot as posted/i }).click()
  await expect(dialog).not.toBeVisible()
  await expect(
    page.getByText(/nothing in the queue yet/i),
  ).toBeVisible({ timeout: 4000 })
})
