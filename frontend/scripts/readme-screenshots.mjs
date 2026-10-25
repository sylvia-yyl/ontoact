// README screenshots, in the order a user would go: ontology, plan, actions, explanation, outage, package apply and revert.
//
//   node scripts/readme-screenshots.mjs <dataco ontology> <dataco app> [<container ontology> <container app>]
//
// Ids are printed by scripts/seed_case.py. BASE_URL defaults to http://localhost:5173; SHOTS to ../docs/images.
import { chromium } from 'playwright'

const base = process.env.BASE_URL ?? 'http://localhost:5173'
const dir = process.env.SHOTS ?? '../docs/images'
const [ontology, app, containerOntology, containerApp] = process.argv.slice(2)
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const errors = []
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) errors.push(`${r.status()} ${r.url()}`) })
const W = () => page.getByTestId('workshop-app')
const shot = async (name, full = true) => { await page.waitForTimeout(2000); await page.screenshot({ path: `${dir}/${name}.png`, fullPage: full }) }
const open = async pageId => { await page.goto(`${base}/apps/workshop/${app}?ontology=${ontology}&page=${pageId}`, { waitUntil: 'networkidle' }); await page.waitForTimeout(1500) }
const pick = async label => { await W().getByText(label).first().click(); await page.waitForTimeout(1000) }

await page.goto(`${base}/ontology?ontology=${ontology}`, { waitUntil: 'networkidle' }); await shot('01-ontology', false)
await open('cockpit'); await shot('02-cockpit')
await open('coverage'); await shot('03-coverage')
await open('actions'); await pick('Allocate Cold'); await shot('04-tradeoff')
await pick('rework for Gun Fire Safe'); await shot('05-cross-line')
await pick('Allocate Cold')
if (await W().getByRole('button', { name: 'Explain' }).count()) await W().getByRole('button', { name: 'Explain' }).click()
await page.getByText(/^Evidence \(/).first().waitFor({ timeout: 120000 }); await shot('06-explanation')
await open('outage'); await pick('rework for Gun Fire Safe'); await shot('07-outage')
await open('actions'); await pick('Allocate Cold')
if (await W().getByPlaceholder('Why this option').count()) {
  await W().getByPlaceholder('Why this option').fill('Steel goes where it earns most per sheet. We accept the slip on safes and kayaks this quarter.')
  await W().getByRole('button', { name: 'Create decision package' }).click(); await page.waitForTimeout(2500)
}
await shot('08-package')
await W().getByRole('button', { name: 'Apply to ontology' }).click()
await page.waitForSelector('text=/Revert ontology changes/', { timeout: 120000 }); await shot('09-applied')
await W().getByRole('button', { name: 'Revert ontology changes' }).click()
await page.waitForSelector('text=/Reverted/', { timeout: 120000 }); await shot('10-reverted')
if (containerApp) { await page.goto(`${base}/apps/workshop/${containerApp}?ontology=${containerOntology}`, { waitUntil: 'networkidle' }); await shot('11-container', false) }
console.log(JSON.stringify({ errors }))
await browser.close()
