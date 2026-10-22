import type { QueryClient } from '@tanstack/react-query'
import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { getProjectOptions } from '@/api/generated/@tanstack/react-query.gen'
import type { ProjectRead } from '@/api/generated/types.gen'
import { makeProject, makeReview } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ReviewPanel } from './ReviewPanel'

describe('ReviewPanel', () => {
  it('shows the summary, three tags and the risk checklist when complete', () => {
    const review = makeReview()
    renderWithQueryClient(<ReviewPanel project={makeProject({ review })} />)

    expect(screen.getByText(review.summary)).toBeInTheDocument()
    const tags = within(screen.getByRole('list', { name: 'Tags' })).getAllByRole('listitem')
    expect(tags.map((tag) => tag.textContent)).toEqual(review.tags)
    for (const risk of review.risks) expect(screen.getByText(risk)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-run review' })).toBeEnabled()
  })

  it('says when no risks were found', () => {
    renderWithQueryClient(
      <ReviewPanel project={makeProject({ review: makeReview({ risks: [] }) })} />,
    )

    expect(screen.getByText('No risks identified.')).toBeInTheDocument()
  })

  it('says when a completed review has no data', () => {
    renderWithQueryClient(<ReviewPanel project={makeProject({ review: null })} />)

    expect(screen.getByText('The review finished but returned no data.')).toBeInTheDocument()
  })

  it('shows progress and no run button while pending', () => {
    renderWithQueryClient(
      <ReviewPanel project={makeProject({ review_status: 'pending', review: null })} />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('Analyzing project…')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the stored error verbatim with a retry button', () => {
    const reviewError = 'AuthenticationError: invalid x-api-key (request_id=req_123)'
    renderWithQueryClient(
      <ReviewPanel
        project={makeProject({ review_status: 'error', review: null, review_error: reviewError })}
      />,
    )

    expect(screen.getByText('Review failed')).toBeInTheDocument()
    expect(screen.getByText(reviewError)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry review' })).toBeEnabled()
  })

  it('explains an interrupted review and offers to run it', () => {
    renderWithQueryClient(
      <ReviewPanel
        project={makeProject({
          review_status: 'unreviewed',
          review: null,
          review_updated_at: null,
        })}
      />,
    )

    expect(screen.getByText('Review was interrupted')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run review' })).toBeEnabled()
  })

  it('starts a review and caches the pending project', async () => {
    const project = makeProject({ review_status: 'error', review: null, review_error: 'boom' })
    const pending: ProjectRead = { ...project, review_status: 'pending', review_error: null }
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json(pending, { status: 202 }),
      ),
    )
    const { user, queryClient } = renderWithQueryClient(<ReviewPanel project={project} />)

    await user.click(screen.getByRole('button', { name: 'Retry review' }))

    await expect.poll(() => cachedProject(queryClient, project.id)?.review_status).toBe('pending')
  })

  it('treats a 409 as "already running" and refetches instead of showing an error', async () => {
    const project = makeProject({ review_status: 'unreviewed', review: null })
    const pending: ProjectRead = { ...project, review_status: 'pending' }
    let refetched = false
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json({ detail: 'already in progress' }, { status: 409 }),
      ),
      http.get(`*/api/projects/${project.id}`, () => {
        refetched = true
        return HttpResponse.json(pending)
      }),
    )
    const { user, queryClient } = renderWithQueryClient(<ReviewPanel project={project} />)

    await user.click(screen.getByRole('button', { name: 'Run review' }))

    await expect.poll(() => cachedProject(queryClient, project.id)?.review_status).toBe('pending')
    expect(refetched).toBe(true)
    expect(screen.queryByText("Couldn't start the review")).not.toBeInTheDocument()
  })

  it('shows other failures to start a review', async () => {
    const project = makeProject()
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json({ detail: 'Database is locked' }, { status: 500 }),
      ),
    )
    const { user } = renderWithQueryClient(<ReviewPanel project={project} />)

    await user.click(screen.getByRole('button', { name: 'Re-run review' }))

    expect(await screen.findByText("Couldn't start the review")).toBeInTheDocument()
    expect(screen.getByText('Database is locked')).toBeInTheDocument()
  })
})

function cachedProject(queryClient: QueryClient, projectId: number): ProjectRead | undefined {
  return queryClient.getQueryData(getProjectOptions({ path: { project_id: projectId } }).queryKey)
}
