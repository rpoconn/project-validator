import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProjectRead } from '@/api/generated/types.gen'
import { REVIEW_POLL_INTERVAL_MS } from '@/api/projects'
import { makeProject, makeReview } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ProjectDetail } from './ProjectDetail'

function renderDetail(projectId: number) {
  const onEdit = vi.fn<(project: ProjectRead) => void>()
  const onDeleted = vi.fn<() => void>()
  const result = renderWithQueryClient(
    <ProjectDetail projectId={projectId} onEdit={onEdit} onDeleted={onDeleted} />,
  )
  return { ...result, onEdit, onDeleted }
}

function serveProject(...responses: ProjectRead[]) {
  const [first] = responses
  let calls = 0
  server.use(
    http.get(`*/api/projects/${first!.id}`, () =>
      HttpResponse.json(responses[Math.min(calls++, responses.length - 1)]),
    ),
  )
}

describe('ProjectDetail', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the project fields and its timeline in due-date order', async () => {
    const project = makeProject({
      title: 'Clinic booking',
      description: 'Rebuild the booking flow.',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [
        { goal: 'Launch', due_at: '2027-02-01T00:00:00Z' },
        { goal: 'Beta', due_at: '2026-12-01T00:00:00Z' },
      ],
    })
    serveProject(project)

    renderDetail(project.id)

    expect(await screen.findByRole('heading', { name: 'Clinic booking' })).toBeInTheDocument()
    expect(screen.getByText('$10,000 – $25,000')).toBeInTheDocument()
    expect(screen.getByText('Rebuild the booking flow.')).toBeInTheDocument()
    const milestones = within(screen.getByRole('list', { name: 'Milestones' })).getAllByRole(
      'listitem',
    )
    expect(milestones.map((item) => item.textContent)).toEqual([
      'BetaDec 1, 2026',
      'LaunchFeb 1, 2027',
    ])
  })

  it('says when there is no timeline', async () => {
    const project = makeProject({ timeline: [] })
    serveProject(project)

    renderDetail(project.id)

    expect(await screen.findByText('No timeline entries')).toBeInTheDocument()
  })

  it('polls while the review is pending and shows the result when it completes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const pending = makeProject({ review_status: 'pending', review: null })
    const review = makeReview({ summary: 'Finished summary.' })
    serveProject(pending, { ...pending, review_status: 'complete', review })

    renderDetail(pending.id)

    expect(await screen.findByText('Analyzing project…')).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    expect(await screen.findByText('Finished summary.')).toBeInTheDocument()
  })

  it('opens the editor with the current project', async () => {
    const project = makeProject({ title: 'Clinic booking' })
    serveProject(project)
    const { user, onEdit } = renderDetail(project.id)

    await user.click(await screen.findByRole('button', { name: 'Edit' }))

    expect(onEdit).toHaveBeenCalledWith(project)
  })

  it('disables editing while a review is running', async () => {
    const project = makeProject({ review_status: 'pending', review: null })
    serveProject(project)

    renderDetail(project.id)

    expect(await screen.findByRole('button', { name: 'Edit' })).toBeDisabled()
  })

  it('deletes the project after confirmation', async () => {
    const project = makeProject({ title: 'Clinic booking' })
    serveProject(project)
    let deleted = false
    server.use(
      http.delete(`*/api/projects/${project.id}`, () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const { user, onDeleted } = renderDetail(project.id)

    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    const prompt = await screen.findByRole('alertdialog', { name: 'Delete “Clinic booking”?' })

    // Backing out leaves the project alone.
    await user.click(within(prompt).getByRole('button', { name: 'Keep project' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(deleted).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete project' }))

    await vi.waitFor(() => expect(onDeleted).toHaveBeenCalledOnce())
    expect(deleted).toBe(true)
  })

  it('keeps the prompt open with the reason when deleting fails', async () => {
    const project = makeProject()
    serveProject(project)
    server.use(
      http.delete(`*/api/projects/${project.id}`, () =>
        HttpResponse.json({ detail: 'Database is locked' }, { status: 500 }),
      ),
    )
    const { user, onDeleted } = renderDetail(project.id)

    await user.click(await screen.findByRole('button', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete project' }))

    expect(await screen.findByText(/Couldn't delete the project: Database is locked/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
    expect(onDeleted).not.toHaveBeenCalled()
  })

  it('reports a missing project', async () => {
    server.use(
      http.get('*/api/projects/999', () =>
        HttpResponse.json({ detail: 'Project 999 not found' }, { status: 404 }),
      ),
    )

    renderDetail(999)

    expect(await screen.findByText('Project not found')).toBeInTheDocument()
    expect(screen.getByText('Project 999 not found')).toBeInTheDocument()
  })
})
