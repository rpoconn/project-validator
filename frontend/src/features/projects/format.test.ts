import { describe, expect, it } from 'vitest'

import { formatBudgetRange, formatDate, formatDateTime, formatDueDate } from './format'

describe('formatBudgetRange', () => {
  it('shows a single amount when the bounds are equal', () => {
    expect(formatBudgetRange(5000, 5000)).toBe('$5,000')
    expect(formatBudgetRange(0, 0)).toBe('$0')
  })

  it('joins the bounds with an en dash', () => {
    expect(formatBudgetRange(5000, 12000)).toBe('$5,000 – $12,000')
  })

  it('shows whole dollars only', () => {
    expect(formatBudgetRange(1999.6, 2500.4)).toBe('$2,000 – $2,500')
  })
})

describe('formatDueDate', () => {
  it('shows the UTC calendar day whatever the local timezone', () => {
    expect(formatDueDate('2026-12-01T00:00:00Z')).toBe('Dec 1, 2026')
    expect(formatDueDate('2026-12-01T23:59:59Z')).toBe('Dec 1, 2026')
  })
})

describe('formatDate and formatDateTime', () => {
  const iso = '2026-10-20T12:00:30Z'

  it('formats in the local timezone with the medium date style', () => {
    const expected = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(new Date(iso))

    expect(formatDate(iso)).toBe(expected)
    expect(formatDate(iso)).toMatch(/^[A-Z][a-z]{2} \d{1,2}, \d{4}$/)
  })

  it('adds a short time to the date', () => {
    const expected = new Intl.DateTimeFormat('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso))

    expect(formatDateTime(iso)).toBe(expected)
    expect(formatDateTime(iso)).toMatch(/^[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M$/)
  })
})
