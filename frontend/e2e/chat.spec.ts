import { expect, test, type Page } from '@playwright/test'

const SHOTS = process.env.SCREENSHOT_DIR

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false })
}

async function register(page: Page) {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`
  await page.goto('/register')
  await page.getByLabel('Name').fill('Ama Mensah')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery-9')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('heading', { name: 'What are you working on?' })).toBeVisible()
  return email
}

test('auth pages and validation', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login$/)
  await shot(page, '01-login')
  await page.getByLabel('Email', { exact: true }).fill('nobody@example.com')
  await page.getByLabel('Password', { exact: true }).fill('wrong-password-123')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password.')

  await page.goto('/register')
  await page.getByLabel('Email', { exact: true }).fill(`weak-${Date.now()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill('12345678')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
})

test('full conversation lifecycle with a real model', async ({ page }) => {
  await register(page)
  await shot(page, '02-empty-state')
  // Without a search API key the web toggle is visibly unavailable rather than silently doing nothing.
  await expect(page.getByRole('button', { name: 'Web search is not configured on this workspace' })).toBeDisabled()

  const composer = page.getByLabel('Message', { exact: true })
  await composer.fill('Reply with a short Python function that adds two numbers, in a fenced code block.')
  await composer.press('Enter')

  await expect(page).toHaveURL(/\/c\/\d+$/)
  await expect(page.getByRole('button', { name: /copy code/i })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible() // reply finished
  await expect(page.getByText(/ in \/ .* out/)).toBeVisible() // token usage shown
  await shot(page, '03-conversation')

  // Follow-up uses history
  await composer.fill('Now rename the function to add_numbers. Reply with only the code.')
  await composer.press('Enter')
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible()
  await expect(page.locator('.prose-chat').last()).toContainText('add_numbers')

  // Rename via sidebar menu
  const nav = page.getByRole('navigation', { name: 'Conversations' })
  await nav.getByRole('button', { name: /^Options for/ }).first().click()
  await page.getByRole('menuitem', { name: 'Rename' }).click()
  await page.getByLabel('Conversation title').fill('Python helpers')
  await page.getByLabel('Conversation title').press('Enter')
  await expect(nav.getByRole('link', { name: 'Python helpers' })).toBeVisible()

  // Search finds it by message content
  await page.getByLabel('Search conversations').fill('add_numbers')
  await expect(nav.getByRole('link', { name: 'Python helpers' })).toBeVisible()
  await page.getByLabel('Search conversations').fill('zzzz-no-match')
  await expect(nav.getByText('No conversations match your search.')).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()

  // Export downloads real content
  const download = page.waitForEvent('download')
  await nav.getByRole('button', { name: 'Options for Python helpers' }).click()
  await page.getByRole('menuitem', { name: 'Export Markdown' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('python-helpers.md')

  // Archive, then restore
  await nav.getByRole('button', { name: 'Options for Python helpers' }).click()
  await page.getByRole('menuitem', { name: 'Archive' }).click()
  await expect(page).toHaveURL(/\/$/)
  await nav.getByRole('tab', { name: 'Archived' }).click()
  await nav.getByRole('button', { name: 'Options for Python helpers' }).click()
  await page.getByRole('menuitem', { name: 'Unarchive' }).click()
  await nav.getByRole('tab', { name: 'Recent' }).click()

  // Delete with confirmation
  await nav.getByRole('button', { name: 'Options for Python helpers' }).click()
  await page.getByRole('menuitem', { name: 'Delete' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Delete' }).click()
  await expect(nav.getByText('No conversations yet.')).toBeVisible()
})

test('stop, regenerate, edit and settings', async ({ page }) => {
  await register(page)
  const composer = page.getByLabel('Message', { exact: true })
  await composer.fill('Write a 600-word story about a lighthouse keeper in Cape Coast.')
  await composer.press('Enter')
  await expect(page.locator('.prose-chat').last()).toBeVisible() // first words have arrived
  await page.getByRole('button', { name: 'Stop generating' }).click()
  await expect(page.getByText(/^Stopped/)).toBeVisible()

  // Regenerate the stopped reply (actions on the latest reply are always visible)
  await page.getByRole('button', { name: 'Regenerate reply' }).click()
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible()

  // Edit the user message -> new reply
  await page.getByRole('region', { name: 'Messages' }).getByText('Write a 600-word story').hover()
  await page.getByRole('button', { name: 'Edit message' }).click()
  await page.getByLabel('Edit message', { exact: true }).fill('Reply with exactly the word: edited')
  await page.getByRole('button', { name: 'Save & regenerate' }).click()
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible()
  await expect(page.locator('.prose-chat').last()).toContainText(/edited/i)

  // Settings: usage reflects real calls; theme switch
  await page.getByRole('link', { name: /Ama Mensah/ }).click()
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Tokens in the last 24 hours' })).toBeVisible()
  await page.getByRole('radio', { name: 'Dark' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await shot(page, '04-settings-dark')
  await page.goto('/')
  await shot(page, '05-empty-dark')
})

test('mobile layout @mobile', async ({ page }) => {
  await register(page)
  await shot(page, '06-mobile-empty')
  await page.getByLabel('Message', { exact: true }).fill('In one sentence, what is Accra?')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('button', { name: 'Regenerate reply' })).toBeVisible()
  await expect(page.locator('.prose-chat').last()).toContainText(/Accra/i)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  expect(overflow).toBe(false)
  await shot(page, '07-mobile-chat')
  await page.getByRole('button', { name: 'Open sidebar' }).first().click()
  await expect(page.getByRole('navigation', { name: 'Conversations' })).toBeVisible()
  await shot(page, '08-mobile-sidebar')
})
