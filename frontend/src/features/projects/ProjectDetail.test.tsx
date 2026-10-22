import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ProjectRead } from '@/api/generated/types.gen'
import { REVIEW_POLL_INTERVAL_MS } from '@/api/projects'
import { makeProject, makeReview } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ProjectDetail } from './ProjectDetail'

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

    renderWithQueryClient(<ProjectDetail projectId={project.id} />)

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

    renderWithQueryClient(<ProjectDetail projectId={project.id} />)

    expect(await screen.findByText('No timeline entries')).toBeInTheDocument()
  })

  it('polls while the review is pending and shows the result when it completes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const pending = makeProject({ review_status: 'pending', review: null })
    const review = makeReview({ summary: 'Finished summary.' })
    serveProject(pending, { ...pending, review_status: 'complete', review })

    renderWithQueryClient(<ProjectDetail projectId={pending.id} />)

    expect(await screen.findByText('Analyzing project…')).toBeInTheDocument()
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    expect(await screen.findByText('Finished summary.')).toBeInTheDocument()
  })

  it('reports a missing project', async () => {
    server.use(
      http.get('*/api/projects/999', () =>
        HttpResponse.json({ detail: 'Project 999 not found' }, { status: 404 }),
      ),
    )

    renderWithQueryClient(<ProjectDetail projectId={999} />)

    expect(await screen.findByText('Project not found')).toBeInTheDocument()
    expect(screen.getByText('Project 999 not found')).toBeInTheDocument()
  })
})
