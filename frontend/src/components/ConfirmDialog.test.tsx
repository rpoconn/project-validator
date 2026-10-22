import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from './ConfirmDialog'

function renderConfirm(props: Partial<React.ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn<() => void>()
  const onOpenChange = vi.fn<(open: boolean) => void>()
  const user = userEvent.setup({ delay: null })
  render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title="Delete this?"
      description="It cannot be undone."
      confirmLabel="Delete"
      onConfirm={onConfirm}
      {...props}
    />,
  )
  return { user, onConfirm, onOpenChange }
}

describe('ConfirmDialog', () => {
  it('confirms without closing by itself', async () => {
    const { user, onConfirm, onOpenChange } = renderConfirm()

    expect(screen.getByRole('alertdialog', { name: 'Delete this?' })).toBeInTheDocument()
    expect(screen.getByText('It cannot be undone.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onOpenChange).not.toHaveBeenCalled()
  })

  it('cancels with the button and with Escape', async () => {
    const onCancel = vi.fn<() => void>()
    const { user, onConfirm, onOpenChange } = renderConfirm({ cancelLabel: 'Keep', onCancel })

    await user.click(screen.getByRole('button', { name: 'Keep' }))
    expect(onCancel).toHaveBeenCalledOnce()
    expect(onOpenChange).toHaveBeenLastCalledWith(false)

    await user.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledTimes(2)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('blocks closing and the buttons while pending', async () => {
    const { user, onConfirm, onOpenChange } = renderConfirm({ pending: true })

    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.keyboard('{Escape}')

    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
