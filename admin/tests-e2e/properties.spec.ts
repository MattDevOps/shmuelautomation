import { expect, test, type Page } from '@playwright/test'

interface PropertyRecord {
  id: string
  type: 'rent' | 'sale'
  status: 'available' | 'rented' | 'sold'
  price: string
  currency: string
  rooms: string | null
  size_sqm: number | null
  floor: number | null
  address: string | null
  neighborhood: string | null
  city: string
  owner_name: string | null
  owner_phone: string | null
  broker_fee_status: 'yes' | 'no' | 'partial'
  broker_fee_amount: string | null
  description: string | null
  notes: string | null
  yad2_url: string | null
  created_at: string
  updated_at: string
}

function makeProperty(overrides: Partial<PropertyRecord> = {}): PropertyRecord {
  return {
    id: 'p1',
    type: 'rent',
    status: 'available',
    price: '8500.00',
    currency: 'ILS',
    rooms: '3.5',
    size_sqm: 80,
    floor: null,
    address: null,
    neighborhood: 'Baka',
    city: 'Jerusalem',
    owner_name: 'Yossi',
    owner_phone: null,
    broker_fee_status: 'yes',
    broker_fee_amount: null,
    description: null,
    notes: null,
    yad2_url: null,
    created_at: '2026-05-03T00:00:00',
    updated_at: '2026-05-03T00:00:00',
    ...overrides,
  }
}

async function mockBackend(page: Page, store: Map<string, PropertyRecord>) {
  await page.route(/\/properties(\?.*)?$/, async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/properties') && route.request().method() === 'GET') {
      const t = url.searchParams.get('type')
      const s = url.searchParams.get('status')
      const rows = [...store.values()].filter(
        (p) => (!t || p.type === t) && (!s || p.status === s),
      )
      await route.fulfill({ json: rows })
      return
    }
    if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}') as Partial<PropertyRecord>
      const id = `p${store.size + 1}`
      const next = makeProperty({ ...body, id })
      store.set(id, next)
      await route.fulfill({ status: 201, json: next })
      return
    }
    await route.continue()
  })

  await page.route(/\/properties\/[\w-]+$/, async (route) => {
    const id = route.request().url().split('/').pop()!.split('?')[0]!
    const method = route.request().method()
    const existing = store.get(id)

    if (method === 'GET') {
      if (!existing) return route.fulfill({ status: 404, json: { detail: 'not found' } })
      return route.fulfill({ json: existing })
    }
    if (method === 'PATCH') {
      if (!existing) return route.fulfill({ status: 404, json: { detail: 'not found' } })
      const body = JSON.parse(route.request().postData() ?? '{}') as Partial<PropertyRecord>
      const next = { ...existing, ...body }
      store.set(id, next)
      return route.fulfill({ json: next })
    }
    if (method === 'DELETE') {
      store.delete(id)
      return route.fulfill({ status: 204 })
    }
    await route.continue()
  })
}

test('import from yad2 prefills the form, then saves the property', async ({
  page,
}) => {
  const store = new Map<string, PropertyRecord>()
  await mockBackend(page, store)

  await page.route('**/properties/import/yad2', async (route) => {
    await route.fulfill({
      json: {
        url: 'https://www.yad2.co.il/realestate/item/abc',
        title: 'דירת 4 חדרים, בקעה',
        description: 'Bright apartment',
        price: '3200000',
        rooms: '4',
        size_sqm: 95,
        floor: 2,
        address: 'Emek Refaim 12',
        neighborhood: 'Baka',
        image_urls: ['https://img.yad2.co.il/p1.jpg'],
        warnings: [],
      },
    })
  })

  await page.goto('/import')
  await page
    .getByRole('textbox', { name: /yad2 url/i })
    .fill('https://www.yad2.co.il/realestate/item/abc')
  await page.getByRole('button', { name: /^fetch$/i }).click()

  await expect(
    page.getByRole('heading', { name: /review and save/i }),
  ).toBeVisible()
  await expect(page.getByRole('spinbutton', { name: /^price$/i })).toHaveValue(
    '3200000',
  )
  await expect(
    page.getByRole('textbox', { name: /^neighborhood$/i }),
  ).toHaveValue('Baka')

  await page.getByRole('button', { name: /create property/i }).click()

  await expect(page.getByRole('heading', { name: 'Properties' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Baka', exact: true })).toBeVisible()
})

test('create, edit, flip status, delete', async ({ page }) => {
  const store = new Map<string, PropertyRecord>()
  await mockBackend(page, store)

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Properties' })).toBeVisible()
  await expect(page.getByText(/no properties match/i)).toBeVisible()

  // Create — admin lands on the new property's edit page (so photos can be added)
  await page.getByRole('link', { name: /new property/i }).click()
  await page.getByRole('spinbutton', { name: /^price$/i }).fill('8500')
  await page.getByRole('textbox', { name: /^neighborhood$/i }).fill('Baka')
  await page.getByRole('textbox', { name: /^owner name$/i }).fill('Yossi')
  await page.getByRole('button', { name: 'Create' }).click()

  // Land on the edit page with the new property pre-loaded
  await expect(page.getByRole('heading', { name: /edit property/i })).toBeVisible()
  await expect(page.getByRole('textbox', { name: /^neighborhood$/i })).toHaveValue('Baka')

  // Navigate to the list to verify the new row + flip status
  await page.getByRole('link', { name: /^properties$/i }).click()
  await expect(page.getByRole('cell', { name: 'Baka', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Yossi', exact: true })).toBeVisible()

  // Flip status to rented
  await page
    .getByRole('combobox', { name: /status for baka/i })
    .selectOption('rented')
  await expect(
    page.getByRole('combobox', { name: /status for baka/i }),
  ).toHaveValue('rented')

  // Edit and change owner
  await page.getByRole('link', { name: 'Edit' }).click()
  const owner = page.getByRole('textbox', { name: /^owner name$/i })
  await owner.fill('Avi')
  await page.getByRole('button', { name: /save changes/i }).click()
  await expect(page.getByRole('cell', { name: 'Avi', exact: true })).toBeVisible()

  // Delete
  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: /delete baka/i }).click()
  await expect(page.getByText(/no properties match/i)).toBeVisible()
})
