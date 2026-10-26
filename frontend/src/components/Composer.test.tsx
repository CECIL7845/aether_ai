import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Composer } from './Composer'

describe('Composer', () => {
  it('sends on Enter and inserts a newline on Shift+Enter', async () => {
    const onSend = vi.fn().mockResolvedValue(null)
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />)
    const box = screen.getByLabelText('Message')
    await userEvent.type(box, 'line one{Shift>}{Enter}{/Shift}line two{Enter}')
    expect(onSend).toHaveBeenCalledWith('line one\nline two')
    expect(box).toHaveValue('')
  })

  it('does not send blank messages', async () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />)
    await userEvent.type(screen.getByLabelText('Message'), '   {Enter}')
    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
  })

  it('restores the text when the send is rejected', async () => {
    const onSend = vi.fn().mockResolvedValue('Too many requests.')
    render(<Composer onSend={onSend} onStop={() => {}} streaming={false} />)
    await userEvent.type(screen.getByLabelText('Message'), 'hello{Enter}')
    expect(screen.getByLabelText('Message')).toHaveValue('hello')
  })

  it('shows a stop button while streaming', async () => {
    const onStop = vi.fn()
    render(<Composer onSend={vi.fn()} onStop={onStop} streaming />)
    await userEvent.click(screen.getByRole('button', { name: 'Stop generating' }))
    expect(onStop).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Send message' })).toBeNull()
  })
})
