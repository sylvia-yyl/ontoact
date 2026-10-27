import { chromium } from 'playwright'

const base = process.env.BASE_URL ?? 'http://localhost:5173'
const [ontology, app] = process.argv.slice(2)
if (!ontology || !app) throw new Error('Usage: node scripts/interaction-smoke.mjs <ontology> <app>')

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const failures = []
page.on('pageerror', error => failures.push(`page error: ${error.message}`))
page.on('response', response => {
  if (response.url().includes('/api/') && response.status() >= 500) failures.push(`${response.status()} ${response.url()}`)
})

const url = `${base}/apps/workshop/${app}?ontology=${ontology}`
await page.goto(url, { waitUntil: 'networkidle' })
const appRoot = page.getByTestId('workshop-app')
await appRoot.waitFor()

// Users can visit pages in any order, including repeatedly, without relying on a scripted workflow.
const pages = await appRoot.getByRole('navigation', { name: 'Pages' }).getByRole('button').allTextContents()
for (const title of [...pages].reverse().concat(pages.slice(0, 2))) {
  await appRoot.getByRole('button', { name: title, exact: true }).click()
  await page.waitForTimeout(150)
  if (await page.getByText('This page could not load').count()) failures.push(`page crashed after opening ${title}`)
}

// Unknown page ids fall back to the first configured page instead of leaving a dead screen.
await page.goto(`${url}&page=does-not-exist`, { waitUntil: 'networkidle' })
await appRoot.waitFor()

// Repeated refresh attempts must not create a permanently stuck or crashing UI.
const reload = appRoot.getByRole('button', { name: /Reload data|Reloading/ })
await reload.click()
await page.waitForFunction(() => ![...document.querySelectorAll('button')].some(button => button.textContent?.includes('Reloading')))
await reload.click()
await page.waitForFunction(() => ![...document.querySelectorAll('button')].some(button => button.textContent?.includes('Reloading')))

// Exercise independent controls in combinations and return them to stable defaults.
const time = appRoot.getByRole('combobox', { name: 'Time range' })
if (await time.isEnabled()) {
  for (const value of ['30d', '90d', 'all']) await time.selectOption(value)
}
for (const value of ['5', '0']) await appRoot.getByRole('combobox', { name: 'Refresh' }).selectOption(value)

// Action selection is URL state: switch between several actions, leave, and return.
const actionsTab = appRoot.getByRole('button', { name: 'Actions', exact: true })
if (await actionsTab.count()) {
  await actionsTab.click()
  const actions = appRoot.getByTestId('action-list').getByRole('button')
  const count = Math.min(await actions.count(), 4)
  for (let index = count - 1; index >= 0; index -= 1) await actions.nth(index).click()

  const rationale = appRoot.getByPlaceholder('Why this option')
  if (await rationale.count()) {
    const create = appRoot.getByRole('button', { name: 'Create decision package' })
    if (await create.isEnabled()) failures.push('decision package enabled without rationale')
    await rationale.fill('Interaction smoke test; changes must be safely reversible.')
    if (!(await create.isEnabled())) failures.push('decision package stayed disabled after valid input')
    else {
      await create.click()
      const apply = appRoot.getByRole('button', { name: 'Apply to ontology' })
      await apply.waitFor({ timeout: 30_000 })
      if (count > 1) {
        await actions.nth(1).click()
        await appRoot.getByText('This run already has an active decision package for another action.').waitFor()
        if (await appRoot.getByRole('button', { name: 'Apply to ontology' }).count()) failures.push('package controls shown under the wrong action')
        await actions.nth(0).click()
        await apply.waitFor()
      }
      await apply.click()
      const revert = appRoot.getByRole('button', { name: 'Revert ontology changes' })
      await revert.waitFor({ timeout: 120_000 })
      await revert.click()
      await appRoot.getByText('Reverted', { exact: true }).waitFor({ timeout: 120_000 })
    }
  }
}

await browser.close()
if (failures.length) throw new Error(failures.join('\n'))
console.log(JSON.stringify({ ok: true, pages }))
