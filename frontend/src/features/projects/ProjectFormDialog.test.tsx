import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectCreate, ProjectRead } from '@/api/generated/types.gen'
import { makeProject } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ProjectFormDialog } from './ProjectFormDialog'

function renderDialog() {
  const onCreated = vi.fn<(project: ProjectRead) => void>()
  const onOpenChange = vi.fn<(open: boolean) => void>()
  const result = renderWithQueryClient(
    <ProjectFormDialog open onOpenChange={onOpenChange} onCreated={onCreated} />,
  )
  return { ...result, onCreated, onOpenChange }
}

async function fillRequiredFields(user: UserEvent) {
  await user.type(screen.getByLabelText('Title'), '  Clinic booking ')
  await user.type(screen.getByLabelText('Description'), 'Rebuild the booking flow.')
  await user.type(screen.getByLabelText('Industry'), 'Healthcare')
  await user.type(screen.getByLabelText('Minimum budget (USD)'), '10000')
  await user.type(screen.getByLabelText('Maximum budget (USD)'), '25000')
}

const submit = (user: UserEvent) =>
  user.click(screen.getByRole('button', { name: 'Create project' }))

describe('ProjectFormDialog', () => {
  it('shows field errors for an empty form without calling the API', async () => {
    // Any request would fail the test: MSW errors on unhandled requests.
    const { user, onCreated } = renderDialog()

    await submit(user)

    for (const label of ['Title', 'Description', 'Industry']) {
      const input = screen.getByLabelText(label)
      expect(input).toHaveAttribute('aria-invalid', 'true')
      expect(input).toHaveAccessibleDescription('Required')
    }
    expect(screen.getByLabelText('Minimum budget (USD)')).toHaveAccessibleDescription('Required')
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('rejects a maximum budget below the minimum', async () => {
    const { user } = renderDialog()
    await fillRequiredFields(user)
    await user.clear(screen.getByLabelText('Maximum budget (USD)'))
    await user.type(screen.getByLabelText('Maximum budget (USD)'), '500')

    await submit(user)

    expect(screen.getByLabelText('Maximum budget (USD)')).toHaveAccessibleDescription(
      'Maximum budget must be at least the minimum',
    )
  })

  it('creates the project with the API payload and reports it', async () => {
    let body: ProjectCreate | undefined
    const created = makeProject({ review_status: 'pending', review: null })
    server.use(
      http.post('*/api/projects', async ({ request }) => {
        body = (await request.json()) as ProjectCreate
        return HttpResponse.json(created, { status: 201 })
      }),
    )
    const { user, onCreated } = renderDialog()
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: 'Add milestone' }))
    await user.type(screen.getByLabelText('Milestone 1 goal'), 'Beta')
    await user.type(screen.getByLabelText('Milestone 1 due date'), '2026-12-01')

    await submit(user)

    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
    expect(body).toEqual({
      title: 'Clinic booking',
      description: 'Rebuild the booking flow.',
      industry: 'Healthcare',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00.000Z' }],
    })
  })

  it('validates and removes milestones', async () => {
    const { user } = renderDialog()
    await user.click(screen.getByRole('button', { name: 'Add milestone' }))

    await submit(user)

    expect(screen.getByLabelText('Milestone 1 goal')).toHaveAccessibleDescription('Required')
    expect(screen.getByLabelText('Milestone 1 due date')).toHaveAccessibleDescription(
      'Choose a date',
    )
    await user.click(screen.getByRole('button', { name: 'Remove milestone 1' }))
    expect(screen.queryByLabelText('Milestone 1 goal')).not.toBeInTheDocument()
  })

  it('maps server validation errors onto fields and the form', async () => {
    server.use(
      http.post('*/api/projects', () =>
        HttpResponse.json(
          {
            detail: [
              { loc: ['body', 'title'], msg: 'Title already used', type: 'value_error' },
              { loc: ['body'], msg: 'Value error, Something about the whole body', type: 'x' },
            ],
          },
          { status: 422 },
        ),
      ),
    )
    const { user, onCreated } = renderDialog()
    await fillRequiredFields(user)

    await submit(user)

    expect(await screen.findByText('Title already used')).toBeInTheDocument()
    expect(screen.getByLabelText('Title')).toHaveAccessibleDescription('Title already used')
    const formAlert = screen.getByText("Couldn't create the project").closest('[role="alert"]')
    expect(
      within(formAlert as HTMLElement).getByText('Something about the whole body'),
    ).toBeVisible()
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('shows other failures at the top of the form', async () => {
    server.use(http.post('*/api/projects', () => HttpResponse.error()))
    const { user } = renderDialog()
    await fillRequiredFields(user)

    await submit(user)

    expect(await screen.findByText(/Could not reach the server/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create project' })).toBeEnabled()
  })
})
