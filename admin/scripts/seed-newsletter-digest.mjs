import { chromium } from 'playwright'

const PROPS = [
  {
    type: 'rent',
    neighborhood: 'Rehavia',
    address: 'Ben Maimon 12',
    price: '9500',
    currency: 'NIS',
    rooms: '4',
    size: '95',
    floor: '2',
    description: 'Bright 4-room rental in Rehavia, walking distance to Gan Sacher.',
  },
  {
    type: 'sale',
    neighborhood: 'Baka',
    address: 'Yehuda 24',
    price: '3200000',
    currency: 'NIS',
    rooms: '3',
    size: '78',
    floor: '1',
    description: 'Charming 3-room apartment for sale in the heart of Baka.',
  },
  {
    type: 'rent',
    neighborhood: 'Nachlaot',
    address: 'Sukkat Shalom 8',
    price: '7200',
    currency: 'NIS',
    rooms: '2',
    size: '55',
    floor: '0',
    description: 'Cozy 2-room ground-floor in Nachlaot, near Mahane Yehuda.',
  },
]

const ADMIN = 'https://admin.classicjerusalem.com'

const browser = await chromium.launch({ headless: false, slowMo: 120 })
const context = await browser.newContext()
const page = await context.newPage()

console.log('[driver] opening admin SPA — Cloudflare Access will prompt for email + PIN')
await page.goto(ADMIN + '/')

console.log('[driver] waiting for you to finish Access login (up to 5 min)…')
await page.waitForURL(
  (url) => url.hostname === 'admin.classicjerusalem.com' && !url.pathname.startsWith('/cdn-cgi'),
  { timeout: 5 * 60 * 1000 },
)
await page.waitForLoadState('networkidle')
console.log('[driver] logged in')

for (let i = 0; i < PROPS.length; i++) {
  const p = PROPS[i]
  console.log(`[driver] creating property ${i + 1}/3: ${p.neighborhood} ${p.type} ${p.price} ${p.currency}`)
  await page.goto(ADMIN + '/new')
  await page.waitForLoadState('networkidle')

  await page.locator('select').nth(0).selectOption(p.type)
  await page.locator('select').nth(1).selectOption('available')

  await page.getByLabel('Price', { exact: false }).fill(p.price)
  await page.getByLabel('Currency').fill(p.currency)
  await page.getByLabel('Rooms').fill(p.rooms)
  await page.getByLabel('Size (sqm)').fill(p.size)
  await page.getByLabel('Floor').fill(p.floor)
  await page.getByLabel('Neighborhood').fill(p.neighborhood)
  await page.getByLabel('Address').fill(p.address)
  await page.getByLabel('Description (public)').fill(p.description)

  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(800)
  console.log(`[driver] saved property ${i + 1}`)
}

console.log('[driver] all 3 created. Watch the inbox for the digest email (should fire on the 3rd save).')
console.log('[driver] keeping browser open for 20s so you can see…')
await page.waitForTimeout(20000)
await browser.close()
console.log('[driver] done')
