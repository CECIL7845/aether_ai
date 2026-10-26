import { expect, test } from '@playwright/test'

// Synthetic sales data; the expected totals are computed independently below.
const CSV = `date,region,product,units,revenue
2026-01-05,Accra,Cement,10,1200.50
2026-01-07,Kumasi,Cement,4,480
2026-02-02,Accra,Paint,7,350
2026-02-10,Tamale,Cement,,0
2026-03-01,Accra,Cement,3,360
2026-03-15,Kumasi,Paint,12,600
`

test('analyse an uploaded CSV with tool-computed numbers and a chart', async ({ page }) => {
  // Several model↔tool rounds on a free-tier model can take minutes.
  test.setTimeout(480_000)
  await page.goto('/register')
  await page.getByLabel('Email', { exact: true }).fill(`data-${Date.now()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery-9')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'What are you working on?' })).toBeVisible()

  await page.getByRole('button', { name: 'Attach documents' }).click()
  await page.getByTestId('file-input').setInputFiles({ name: 'sales.csv', mimeType: 'text/csv', buffer: Buffer.from(CSV) })
  await expect(page.getByRole('list', { name: 'Attached documents' }).getByText('(Ready)')).toBeAttached()

  const composer = page.getByLabel('Message', { exact: true })
  await composer.fill('What is the total revenue per region? Show it as a bar chart.')
  await composer.press('Enter')
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible({ timeout: 420_000 })

  const steps = page.getByLabel('Analysis steps')
  await expect(steps).toContainText('Queried data')
  await expect(page.locator('figure table').first()).toContainText('1,910.5') // Accra = 1200.50 + 350 + 360
  await expect(page.getByRole('img', { name: /bar chart/ })).toBeVisible()
  if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/11-analysis.png`, fullPage: true })

  const download = page.waitForEvent('download')
  await page.getByRole('link', { name: /as CSV/ }).first().click()
  expect((await download).suggestedFilename()).toMatch(/\.csv$/)
})
