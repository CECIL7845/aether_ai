import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('does not render raw HTML from model output', () => {
    const { container } = render(<Markdown content={'Hello <img src=x onerror="alert(1)"> <script>alert(2)</script>'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
  })

  it('opens links in a new tab without leaking the opener', () => {
    render(<Markdown content="[docs](https://example.com)" />)
    const link = screen.getByRole('link', { name: 'docs' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('does not create clickable javascript: links', () => {
    const { container } = render(<Markdown content="[click](javascript:alert(1))" />)
    const href = container.querySelector('a')?.getAttribute('href') ?? ''
    expect(href.startsWith('javascript:')).toBe(false)
  })

  it('renders fenced code with a language label and copy button', () => {
    render(<Markdown content={'```python\nprint("hi")\n```'} />)
    expect(screen.getByText('python')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /copy code/i })).toBeInTheDocument()
  })

  it('renders GFM tables', () => {
    render(<Markdown content={'| a | b |\n|---|---|\n| 1 | 2 |'} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
})
