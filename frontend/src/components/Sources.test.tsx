import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { Message } from '../api/types'
import { Sources } from './Sources'

const base: Message = {
  id: 1, role: 'assistant', content: 'x', status: 'complete', error_kind: '', error_message: '', model_id: 'm',
  stop_reason: 'end', input_tokens: 1, output_tokens: 1, cost_usd: null, citations: [], invalid_citations: [],
  created_at: '2026-10-26T00:00:00Z',
}

describe('Sources', () => {
  it('lists web citations as safe external links and flags snippet-only sources', async () => {
    render(
      <Sources
        message={{
          ...base,
          citations: [
            { ref: 'W1', kind: 'web', document_id: null, url: 'https://bog.gov.gh/rate', title: 'Bank of Ghana', location: 'bog.gov.gh', retrieved: true, snippet: 'Policy rate 25%' },
            { ref: 'W2', kind: 'web', document_id: null, url: 'https://blog.test/p', title: 'A blog', location: 'blog.test', retrieved: false, snippet: '27%?' },
          ],
          grounding: { web: { query: 'policy rate', pages: [{ url: 'https://bog.gov.gh/rate', title: 'x', status: 'read' }, { url: 'https://blog.test/p', title: 'y', status: 'snippet' }], sources: [] } },
        }}
      />,
    )
    expect(screen.getByText(/Searched the web for “policy rate” · read 1 of 2 pages/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /2 sources cited/ }))
    const link = screen.getByRole('link', { name: /Bank of Ghana/ })
    expect(link).toHaveAttribute('href', 'https://bog.gov.gh/rate')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(screen.getByText('snippet only')).toBeInTheDocument()
  })

  it('warns about citations that match no provided source', () => {
    render(<Sources message={{ ...base, invalid_citations: ['S9'] }} />)
    expect(screen.getByRole('note')).toHaveTextContent('cites S9, which does not match any provided source')
  })

  it('renders nothing for an ungrounded reply', () => {
    const { container } = render(<Sources message={base} />)
    expect(container).toBeEmptyDOMElement()
  })
})
