import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ErrorBanner } from './ErrorBanner'

describe('ErrorBanner', () => {
  it('shows the title and message as an alert', () => {
    render(<ErrorBanner title="Could not load" message="The server said no." />)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not load')
    expect(alert).toHaveTextContent('The server said no.')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('offers a retry button that calls back', async () => {
    const onRetry = vi.fn<() => void>()
    const user = userEvent.setup({ delay: null })
    render(<ErrorBanner title="Failed" message="Try again." onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('disables retry while a retry is in flight', () => {
    render(<ErrorBanner title="Failed" message="Try again." onRetry={() => {}} retrying />)

    expect(screen.getByRole('button', { name: 'Retry' })).toBeDisabled()
  })
})
