import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ReviewStatus } from '@/api/generated/types.gen'

import { ReviewStatusBadge } from './ReviewStatusBadge'

describe('ReviewStatusBadge', () => {
  it.each<[ReviewStatus, string]>([
    ['unreviewed', 'Not reviewed'],
    ['pending', 'Reviewing'],
    ['complete', 'Reviewed'],
    ['error', 'Review failed'],
  ])('labels %s as "%s"', (status, label) => {
    render(<ReviewStatusBadge status={status} />)

    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('shows a spinner only while pending', () => {
    const { container, rerender } = render(<ReviewStatusBadge status="pending" />)

    const spinner = container.querySelector('[role="status"]')
    expect(spinner).not.toBeNull()
    expect(spinner).toHaveAttribute('aria-hidden', 'true')

    for (const status of ['unreviewed', 'complete', 'error'] as const) {
      rerender(<ReviewStatusBadge status={status} />)
      expect(container.querySelector('[role="status"]')).toBeNull()
    }
  })
})
