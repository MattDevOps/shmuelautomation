import { expect, test } from '@playwright/test'

const property = {
  id: 'p1',
  type: 'sale',
  status: 'available',
  price: '3200000.00',
  currency: 'ILS',
  rooms: '4',
  size_sqm: 95,
  floor: 2,
  address: '12 Emek Refaim',
  neighborhood: 'Baka',
  city: 'Jerusalem',
  owner_name: 'Yossi',
  owner_phone: null,
  broker_fee_status: 'yes',
  broker_fee_amount: null,
  description: 'Bright top-floor apartment',
  notes: null,
  yad2_url: null,
  created_at: '2026-05-03T00:00:00',
  updated_at: '2026-05-03T00:00:00',
}

const matches = [
  {
    id: 'c1',
    name: 'Yossi Cohen',
    phone: '+972500000001',
    email: null,
    segments: ['buyer', 'baka'],
    match_score: 2,
    match_reasons: ['buyer', 'Baka'],
  },
  {
    id: 'c2',
    name: 'David Stern',
    phone: null,
    email: 'david@example.com',
    segments: ['buyer', 'vip'],
    match_score: 1,
    match_reasons: ['buyer'],
  },
]

const compose = {
  text_en: 'For sale — Baka\n4 rooms · 95 sqm\nILS 3,200,000\n12 Emek Refaim',
  text_he: 'למכירה בBaka\n4 חדרים · 95 מ"ר\nILS 3,200,000',
  whatsapp_share_url: 'https://wa.me/?text=ForSaleBaka',
  facebook_share_url: null,
}

const groups = [
  {
    id: 'g1',
    platform: 'whatsapp',
    audience: 'sale',
    name: 'Jerusalem Sales WA',
    target_url: 'https://chat.whatsapp.com/sales',
    notes: null,
    sort_order: 0,
    active: true,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
  },
]

test('edit page → matching contacts → share-now → group checklist', async ({ page }) => {
  await page.route('**/properties/p1', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: property })
    } else {
      await route.continue()
    }
  })
  await page.route('**/properties/p1/photos', async (route) => {
    await route.fulfill({ json: [] })
  })
  await page.route('**/properties/p1/matching-contacts', async (route) => {
    await route.fulfill({ json: matches })
  })
  await page.route('**/properties/p1/compose', async (route) => {
    await route.fulfill({ json: compose })
  })
  await page.route('**/groups?**', async (route) => {
    await route.fulfill({ json: groups })
  })

  await page.goto('/p1')

  // Form loaded with seeded data
  await expect(page.getByRole('heading', { name: /edit property/i })).toBeVisible()
  await expect(
    page.getByRole('textbox', { name: /^neighborhood$/i }),
  ).toHaveValue('Baka')

  // Matching contacts panel shows the ranked matches
  await expect(
    page.getByRole('heading', { name: /matching contacts/i }),
  ).toBeVisible()
  await expect(page.getByText('Yossi Cohen')).toBeVisible()
  await expect(page.getByText(/matched by/).first()).toContainText('buyer')
  await expect(page.getByText('David Stern')).toBeVisible()

  // Tel link is present for the contact with a phone
  await expect(
    page.getByRole('link', { name: '+972500000001' }),
  ).toBeVisible()

  // Open the share-now flow
  await page.getByRole('button', { name: /compose & share now/i }).click()

  const dialog = page.getByRole('dialog', { name: /share property/i })
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('textarea')).toHaveValue(/for sale — baka/i)

  // Group checklist filtered by audience='sale'
  await expect(dialog.getByText(/whatsapp groups/i)).toBeVisible()
  const cb = dialog.getByRole('checkbox', { name: /jerusalem sales wa/i })
  await cb.check()
  await expect(cb).toBeChecked()

  // Close cleanly (no slot context here, so no Mark posted button to test)
  await dialog.getByRole('button', { name: /close/i }).click()
  await expect(dialog).not.toBeVisible()
})
