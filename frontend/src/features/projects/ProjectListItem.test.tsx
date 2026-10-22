import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { makeProject } from '@/test/factories'

import { ProjectListItem } from './ProjectListItem'

describe('ProjectListItem', () => {
  it('shows the title, industry, budget range and review status', () => {
    const project = makeProject({
      title: 'Clinic booking',
      industry: 'Healthcare',
      budget_min: 10000,
      budget_max: 25000,
      review_status: 'error',
    })

    render(<ProjectListItem project={project} selected={false} onSelect={() => {}} />)

    const button = screen.getByRole('button', { name: /Clinic booking/ })
    expect(button).toHaveTextContent('Healthcare · $10,000 – $25,000')
    expect(button).toHaveTextContent('Review failed')
    expect(button).not.toHaveAttribute('aria-current')
  })

  it('marks the selected project as current', () => {
    render(<ProjectListItem project={makeProject()} selected onSelect={() => {}} />)

    expect(screen.getByRole('button')).toHaveAttribute('aria-current', 'true')
  })

  it('reports its id when clicked', async () => {
    const project = makeProject({ id: 42 })
    const onSelect = vi.fn<(projectId: number) => void>()
    const user = userEvent.setup({ delay: null })
    render(<ProjectListItem project={project} selected={false} onSelect={onSelect} />)

    await user.click(screen.getByRole('button'))

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(42)
  })
})
