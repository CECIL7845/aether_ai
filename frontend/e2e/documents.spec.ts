import { expect, test, type Page } from '@playwright/test'

// Synthetic document; contains a distinctive fact the model cannot know from general knowledge.
const HANDBOOK = `Kwame & Sons Trading — Staff Handbook (synthetic test document)

Opening hours
The Takoradi branch closes at 4:30pm on Fridays and at 6pm on other weekdays.

Leave
Permanent staff receive 23 days of annual leave.
`

async function register(page: Page) {
  await page.goto('/register')
  await page.getByLabel('Email', { exact: true }).fill(`docs-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery-9')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'What are you working on?' })).toBeVisible()
}

test('attach a document and get a cited answer', async ({ page }) => {
  await register(page)
  await page.getByRole('button', { name: 'Attach documents' }).click()
  await page.getByTestId('file-input').setInputFiles({
    name: 'handbook.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(HANDBOOK),
  })
  const chips = page.getByRole('list', { name: 'Attached documents' })
  await expect(chips.getByText('handbook.txt')).toBeVisible()
  await expect(chips.getByText('(Ready)')).toBeAttached({ timeout: 60_000 })

  const composer = page.getByLabel('Message', { exact: true })
  await composer.fill('According to the handbook, what time does the Takoradi branch close on Fridays?')
  await composer.press('Enter')
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible()
  await expect(page.locator('.prose-chat').last()).toContainText('4:30')
  // Attachments carry over from the new chat into the created conversation without a reload.
  await expect(page.getByRole('list', { name: 'Attached documents' }).getByText('handbook.txt')).toBeVisible()
  const sources = page.getByRole('button', { name: /source.* cited/ })
  await expect(sources).toBeVisible()
  await sources.click()
  await expect(page.getByText('Takoradi branch closes at 4:30pm', { exact: false }).last()).toBeVisible()
  if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/09-cited-answer.png` })

  // The document stays attached after reload.
  await page.reload()
  await expect(page.getByRole('list', { name: 'Attached documents' }).getByText('handbook.txt')).toBeVisible()
})

test('documents library: upload, failure reason, delete', async ({ page }) => {
  await register(page)
  await page.getByRole('link', { name: 'Documents' }).click()
  await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible()
  await expect(page.getByText('No documents yet')).toBeVisible()

  await page.getByLabel('Upload documents').setInputFiles([
    { name: 'notes.md', mimeType: 'text/markdown', buffer: Buffer.from('# Notes\nThe pilot starts in March.') },
    { name: 'fake.pdf', mimeType: 'application/pdf', buffer: Buffer.from('MZ this is not a pdf') },
  ])
  // Content that does not match its extension is rejected at upload time with a reason.
  await expect(page.getByRole('alert').filter({ hasText: 'fake.pdf: This file is not a valid PDF.' })).toBeVisible()
  const list = page.getByRole('list', { name: 'Your documents' })
  await expect(list.getByText('notes.md')).toBeVisible()
  await expect(list.getByText('Ready')).toBeVisible({ timeout: 60_000 })
  if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/10-documents.png` })

  await page.getByRole('button', { name: 'Delete notes.md' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByText('No documents yet')).toBeVisible()
})
