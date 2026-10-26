import { describe, expect, it } from 'vitest'
import { dateGroup, formatCost, formatTokens } from './format'

describe('format', () => {
  it('formats tokens and costs', () => {
    expect(formatTokens(950)).toBe('950')
    expect(formatTokens(1500)).toBe('1.5k')
    expect(formatTokens(null)).toBe('—')
    expect(formatCost(null)).toBeNull()
    expect(formatCost('0.0004')).toBe('<$0.01')
    expect(formatCost('1.234')).toBe('$1.23')
  })

  it('groups dates', () => {
    const now = new Date('2026-10-26T15:00:00')
    expect(dateGroup('2026-10-26T09:00:00', now)).toBe('Today')
    expect(dateGroup('2026-10-22T09:00:00', now)).toBe('Previous 7 days')
    expect(dateGroup('2026-09-01T09:00:00', now)).toBe('Older')
  })
})
