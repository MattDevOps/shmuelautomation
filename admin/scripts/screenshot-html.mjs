import { chromium } from 'playwright'

const url = process.argv[2]
const out = process.argv[3] || '/tmp/digest-preview.png'
if (!url) {
  console.error('usage: node screenshot-html.mjs <file://path> [out.png]')
  process.exit(2)
}
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 700, height: 1200 } })
await page.goto(url)
await page.waitForLoadState('networkidle')
await page.screenshot({ path: out, fullPage: true })
await browser.close()
console.log('wrote', out)
