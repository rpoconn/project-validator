import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import App from './App'
import type { HealthResponse, ProjectCreate, ProjectRead } from './api/generated/types.gen'
import { makeProject } from './test/factories'
import { renderWithQueryClient } from './test/render'
import { server } from './test/server'

const healthy = (anthropic_configured: boolean, llm_mock = false) =>
  http.get('*/api/health', () =>
    HttpResponse.json<HealthResponse>({ status: 'ok', anthropic_configured, llm_mock }),
  )

describe('App', () => {
  beforeEach(() => {
    server.use(healthy(true))
  })

  it('warns when the backend has no Anthropic key', async () => {
    server.use(
      healthy(false),
      http.get('*/api/projects', () => HttpResponse.json([])),
    )

    renderWithQueryClient(<App />)

    expect(await screen.findByText('AI reviews are unavailable')).toBeInTheDocument()
  })

  it('says when reviews are mocked instead of warning about the missing key', async () => {
    server.use(
      healthy(false, true),
      http.get('*/api/projects', () => HttpResponse.json([])),
    )

    renderWithQueryClient(<App />)

    expect(await screen.findByText('AI reviews are mocked')).toBeInTheDocument()
    expect(screen.queryByText('AI reviews are unavailable')).not.toBeInTheDocument()
  })

  it('asks the user to pick a project until one is selected', async () => {
    const project = makeProject({ title: 'Clinic booking' })
    server.use(
      http.get('*/api/projects', () => HttpResponse.json([project])),
      http.get(`*/api/projects/${project.id}`, () => HttpResponse.json(project)),
    )
    const { user } = renderWithQueryClient(<App />)

    expect(screen.getByText('Select a project')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Clinic booking/ }))

    expect(await screen.findByRole('heading', { name: 'Clinic booking' })).toBeInTheDocument()
    expect(screen.queryByText('Select a project')).not.toBeInTheDocument()

    // Form ids must not collide with ids used by the detail view.
    await user.click(screen.getByRole('button', { name: 'New project' }))
    const dialog = screen.getByRole('dialog', { name: 'New project' })
    expect(within(dialog).getByLabelText('Title')).toBeInstanceOf(HTMLInputElement)
  })

  it('creates a first project from the empty state and selects it', async () => {
    const projects: ProjectRead[] = []
    server.use(
      http.get('*/api/projects', () => HttpResponse.json(projects)),
      http.post('*/api/projects', async ({ request }) => {
        const body = (await request.json()) as ProjectCreate
        const created = makeProject({ ...body, review_status: 'pending', review: null })
        projects.unshift(created)
        return HttpResponse.json(created, { status: 201 })
      }),
      http.get('*/api/projects/:id', () => HttpResponse.json(projects[0])),
    )
    const { user } = renderWithQueryClient(<App />)

    await user.click(await screen.findByRole('button', { name: 'Create your first project' }))
    const dialog = screen.getByRole('dialog', { name: 'New project' })
    await user.type(within(dialog).getByLabelText('Title'), 'Clinic booking')
    await user.type(within(dialog).getByLabelText('Description'), 'Rebuild the booking flow.')
    await user.type(within(dialog).getByLabelText('Industry'), 'Healthcare')
    await user.type(within(dialog).getByLabelText('Minimum budget (USD)'), '1000')
    await user.type(within(dialog).getByLabelText('Maximum budget (USD)'), '2000')
    await user.click(within(dialog).getByRole('button', { name: 'Create project' }))

    expect(await screen.findByRole('heading', { name: 'Clinic booking' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('Analyzing project…')).toBeInTheDocument()
    const listItem = within(screen.getByRole('list', { name: 'Projects' })).getByRole('button')
    expect(listItem).toHaveAttribute('aria-current', 'true')
  })
})
