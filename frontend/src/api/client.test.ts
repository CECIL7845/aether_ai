import { describe, expect, it } from 'vitest'
import { errorMessage, parseSSE } from './client'

describe('parseSSE', () => {
  it('parses complete events and keeps the partial remainder', () => {
    const { events, rest } = parseSSE('event: delta\ndata: {"text":"Hi"}\n\nevent: done\ndata: {"status":"comp')
    expect(events).toEqual([{ event: 'delta', data: { text: 'Hi' } }])
    expect(rest).toBe('event: done\ndata: {"status":"comp')
  })

  it('reassembles an event split across chunks', () => {
    const first = parseSSE('event: delta\ndata: {"te')
    const second = parseSSE(first.rest + 'xt":"lo"}\n\n')
    expect(first.events).toEqual([])
    expect(second.events).toEqual([{ event: 'delta', data: { text: 'lo' } }])
  })

  it('skips malformed JSON instead of throwing', () => {
    expect(parseSSE('event: delta\ndata: {nope\n\n').events).toEqual([])
  })
})

describe('errorMessage', () => {
  it('prefers DRF detail, then the first field error', () => {
    expect(errorMessage({ detail: 'Nope.' })).toBe('Nope.')
    expect(errorMessage({ password: ['This password is too common.'] })).toBe('This password is too common.')
    expect(errorMessage(null, 'fallback')).toBe('fallback')
  })
})
