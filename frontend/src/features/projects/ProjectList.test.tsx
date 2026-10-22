import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectRead } from '@/api/generated/types.gen'
import { makeProject } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ProjectList } from './ProjectList'

function renderList(selectedId: number | null = null) {
  const onSelect = vi.fn<(projectId: number) => void>()
  const onCreate = vi.fn<() => void>()
  const result = renderWithQueryClient(
    <ProjectList selectedId={selectedId} onSelect={onSelect} onCreate={onCreate} />,
  )
  return { ...result, onSelect, onCreate }
}

describe('ProjectList', () => {
  it('shows a loading placeholder, then the projects with their review status', async () => {
    const projects = [
      makeProject({ title: 'Clinic booking', review_status: 'pending', review: null }),
      makeProject({
        title: 'Warehouse robots',
        industry: 'Logistics',
        budget_min: 5000,
        budget_max: 5000,
      }),
    ]
    server.use(http.get('*/api/projects', () => HttpResponse.json<ProjectRead[]>(projects)))

    renderList()

    expect(screen.getByLabelText('Loading projects')).toBeInTheDocument()
    const items = await screen.findAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Clinic booking')
    expect(items[0]).toHaveTextContent('Reviewing')
    expect(items[1]).toHaveTextContent('Logistics · $5,000')
    expect(items[1]).toHaveTextContent('Reviewed')
  })

  it('marks the selected project and reports clicks', async () => {
    const [first, second] = [makeProject(), makeProject()]
    server.use(http.get('*/api/projects', () => HttpResponse.json([first, second])))
    const { user, onSelect } = renderList(first?.id)

    expect(await screen.findByRole('button', { name: new RegExp(first!.title) })).toHaveAttribute(
      'aria-current',
      'true',
    )
    await user.click(screen.getByRole('button', { name: new RegExp(second!.title) }))

    expect(onSelect).toHaveBeenCalledWith(second!.id)
  })

  it('offers to create the first project when there are none', async () => {
    server.use(http.get('*/api/projects', () => HttpResponse.json([])))
    const { user, onCreate } = renderList()

    await user.click(await screen.findByRole('button', { name: 'Create your first project' }))

    expect(screen.getByText('No projects yet')).toBeInTheDocument()
    expect(onCreate).toHaveBeenCalledOnce()
  })

  it('shows a load failure and recovers on retry', async () => {
    let calls = 0
    server.use(
      http.get('*/api/projects', () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json({ detail: 'Database unavailable' }, { status: 503 })
          : HttpResponse.json([makeProject({ title: 'Recovered' })])
      }),
    )
    const { user } = renderList()

    expect(await screen.findByText("Couldn't load projects")).toBeInTheDocument()
    expect(screen.getByText('Database unavailable')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Recovered')).toBeInTheDocument()
  })
})
