import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import type { ProjectCreate, ProjectRead } from '@/api/generated/types.gen'
import { makeProject } from '@/test/factories'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { ProjectFormDialog } from './ProjectFormDialog'

function renderDialog(project?: ProjectRead) {
  const onSaved = vi.fn<(project: ProjectRead) => void>()
  const onOpenChange = vi.fn<(open: boolean) => void>()
  const result = renderWithQueryClient(
    <ProjectFormDialog open onOpenChange={onOpenChange} project={project} onSaved={onSaved} />,
  )
  return { ...result, onSaved, onOpenChange }
}

async function fillRequiredFields(user: UserEvent) {
  await user.type(screen.getByLabelText('Title'), '  Clinic booking ')
  await user.type(screen.getByLabelText('Description'), 'Rebuild the booking flow.')
  await user.type(screen.getByLabelText('Industry'), 'Healthcare')
  await user.type(screen.getByLabelText('Minimum budget (USD)'), '10000')
  await user.type(screen.getByLabelText('Maximum budget (USD)'), '25000')
}

async function addMilestone(user: UserEvent, goal: string, dueDate: string) {
  await user.click(screen.getByRole('button', { name: 'Add milestone' }))
  const index = screen.getAllByLabelText(/Milestone \d+ goal/).length
  await user.type(screen.getByLabelText(`Milestone ${index} goal`), goal)
  await user.type(screen.getByLabelText(`Milestone ${index} due date`), dueDate)
}

const submit = (user: UserEvent, label = 'Create project') =>
  user.click(screen.getByRole('button', { name: label }))

const timelinePrompt = () => screen.queryByRole('alertdialog', { name: 'No milestones yet' })

describe('ProjectFormDialog', () => {
  it('marks every field as required and explains the mark', () => {
    renderDialog()

    const dialog = screen.getByRole('dialog', { name: 'New project' })
    expect(within(dialog).getByText('Required field')).toBeInTheDocument()
    for (const label of ['Title', 'Description', 'Industry', 'Maximum budget (USD)']) {
      expect(screen.getByLabelText(label)).toHaveAttribute('aria-required', 'true')
    }
  })

  it('shows field errors for an empty form without calling the API', async () => {
    // Any request would fail the test: MSW errors on unhandled requests.
    const { user, onSaved } = renderDialog()

    await submit(user)

    for (const label of ['Title', 'Description', 'Industry']) {
      const input = screen.getByLabelText(label)
      expect(input).toHaveAttribute('aria-invalid', 'true')
      expect(input).toHaveAccessibleDescription('Required')
    }
    expect(screen.getByLabelText('Minimum budget (USD)')).toHaveAccessibleDescription('Required')
    expect(screen.getByLabelText('Title')).toHaveFocus()
    expect(timelinePrompt()).not.toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('rejects a maximum budget below the minimum', async () => {
    const { user } = renderDialog()
    await fillRequiredFields(user)
    await user.clear(screen.getByLabelText('Maximum budget (USD)'))
    await user.type(screen.getByLabelText('Maximum budget (USD)'), '500')

    await submit(user)

    const max = screen.getByLabelText('Maximum budget (USD)')
    expect(max).toHaveAttribute('aria-invalid', 'true')
    expect(max).toHaveAccessibleDescription('Maximum budget must be at least the minimum')
    expect(timelinePrompt()).not.toBeInTheDocument()
  })

  it('flags an inverted budget range while typing, before any submit', async () => {
    const { user } = renderDialog()
    const min = screen.getByLabelText('Minimum budget (USD)')
    const max = screen.getByLabelText('Maximum budget (USD)')

    await user.type(min, '500')
    // A blank maximum isn't flagged as "Required" while the user is still entering the minimum.
    expect(max).toHaveAttribute('aria-invalid', 'false')

    await user.type(max, '100')
    expect(max).toHaveAccessibleDescription('Maximum budget must be at least the minimum')

    await user.clear(max)
    await user.type(max, '600')
    expect(max).toHaveAttribute('aria-invalid', 'false')
  })

  it('re-checks the range when only the minimum changes', async () => {
    const { user } = renderDialog()
    await fillRequiredFields(user)
    const min = screen.getByLabelText('Minimum budget (USD)')
    const max = screen.getByLabelText('Maximum budget (USD)')

    await user.clear(min)
    await user.type(min, '30000')
    expect(max).toHaveAccessibleDescription('Maximum budget must be at least the minimum')

    await submit(user)
    await user.clear(min)
    await user.type(min, '20000')
    expect(max).toHaveAttribute('aria-invalid', 'false')
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
    const { user, onSaved } = renderDialog()
    await fillRequiredFields(user)
    await addMilestone(user, 'Beta', '2026-12-01')

    await submit(user)

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(created))
    expect(timelinePrompt()).not.toBeInTheDocument()
    expect(body).toEqual({
      title: 'Clinic booking',
      description: 'Rebuild the booking flow.',
      industry: 'Healthcare',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00.000Z' }],
    })
  })

  it('checks before saving a project with no milestones', async () => {
    let body: ProjectCreate | undefined
    const created = makeProject({ review_status: 'pending', review: null })
    server.use(
      http.post('*/api/projects', async ({ request }) => {
        body = (await request.json()) as ProjectCreate
        return HttpResponse.json(created, { status: 201 })
      }),
    )
    const { user, onSaved } = renderDialog()
    await fillRequiredFields(user)

    await submit(user)

    // Choosing to add one returns to the form with an empty milestone row ready.
    const prompt = await screen.findByRole('alertdialog', { name: 'No milestones yet' })
    await user.click(within(prompt).getByRole('button', { name: 'Add a milestone' }))
    expect(timelinePrompt()).not.toBeInTheDocument()
    expect(screen.getByLabelText('Milestone 1 goal')).toHaveValue('')
    expect(onSaved).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Remove milestone 1' }))
    await submit(user)
    await user.click(await screen.findByRole('button', { name: 'Create anyway' }))

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(created))
    expect(body?.timeline).toEqual([])
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
    const { user, onSaved } = renderDialog()
    await fillRequiredFields(user)
    await addMilestone(user, 'Beta', '2026-12-01')

    await submit(user)

    expect(await screen.findByText('Title already used')).toBeInTheDocument()
    expect(screen.getByLabelText('Title')).toHaveAccessibleDescription('Title already used')
    const formAlert = screen.getByText("Couldn't create the project").closest('[role="alert"]')
    expect(
      within(formAlert as HTMLElement).getByText('Something about the whole body'),
    ).toBeVisible()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('shows other failures at the top of the form', async () => {
    server.use(http.post('*/api/projects', () => HttpResponse.error()))
    const { user } = renderDialog()
    await fillRequiredFields(user)
    await addMilestone(user, 'Beta', '2026-12-01')

    await submit(user)

    expect(await screen.findByText(/Could not reach the server/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create project' })).toBeEnabled()
  })

  describe('closing', () => {
    it('closes straight away when nothing has been entered', async () => {
      const { user, onOpenChange } = renderDialog()

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(onOpenChange).toHaveBeenCalledWith(false)
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    })

    it('asks before discarding entered details, whichever way the dialog is closed', async () => {
      const { user, onOpenChange } = renderDialog()
      await user.type(screen.getByLabelText('Title'), 'Half-written')

      await user.keyboard('{Escape}')

      const prompt = screen.getByRole('alertdialog', { name: 'Discard this project?' })
      expect(
        within(prompt).getByText("The details you've entered haven't been saved."),
      ).toBeVisible()
      expect(onOpenChange).not.toHaveBeenCalled()

      await user.click(within(prompt).getByRole('button', { name: 'Keep editing' }))
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Title')).toHaveValue('Half-written')
      expect(onOpenChange).not.toHaveBeenCalled()

      await user.click(screen.getByRole('button', { name: 'Close' }))
      await user.click(screen.getByRole('button', { name: 'Discard' }))
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  describe('editing', () => {
    const existing = makeProject({
      title: 'Clinic booking',
      description: 'Rebuild the booking flow.',
      industry: 'Healthcare',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00Z' }],
    })

    it('starts from the project and saves changes with PUT', async () => {
      let body: ProjectCreate | undefined
      const saved = { ...existing, title: 'Clinic booking v2', review_status: 'pending' as const }
      server.use(
        http.put(`*/api/projects/${existing.id}`, async ({ request }) => {
          body = (await request.json()) as ProjectCreate
          return HttpResponse.json(saved)
        }),
      )
      const { user, onSaved, onOpenChange } = renderDialog(existing)

      const dialog = screen.getByRole('dialog', { name: 'Edit project' })
      expect(within(dialog).getByLabelText('Title')).toHaveValue('Clinic booking')
      expect(within(dialog).getByLabelText('Minimum budget (USD)')).toHaveValue(10000)
      expect(within(dialog).getByLabelText('Milestone 1 due date')).toHaveValue('2026-12-01')

      // Nothing changed yet, so closing needs no confirmation.
      await user.keyboard('{Escape}')
      expect(onOpenChange).toHaveBeenCalledWith(false)

      await user.type(screen.getByLabelText('Title'), ' v2')
      await submit(user, 'Save changes')

      await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved))
      expect(body).toEqual({
        title: 'Clinic booking v2',
        description: 'Rebuild the booking flow.',
        industry: 'Healthcare',
        budget_min: 10000,
        budget_max: 25000,
        timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00.000Z' }],
      })
    })

    it('asks before discarding changes', async () => {
      const { user, onOpenChange } = renderDialog(existing)
      await user.type(screen.getByLabelText('Title'), ' v2')

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(screen.getByRole('alertdialog', { name: 'Discard your changes?' })).toBeInTheDocument()
      expect(onOpenChange).not.toHaveBeenCalled()
    })

    it('explains a save rejected while a review is running', async () => {
      server.use(
        http.put(`*/api/projects/${existing.id}`, () =>
          HttpResponse.json(
            { detail: `Project ${existing.id} already has a review in progress` },
            { status: 409 },
          ),
        ),
      )
      const { user, onSaved } = renderDialog(existing)
      await user.type(screen.getByLabelText('Title'), ' v2')

      await submit(user, 'Save changes')

      const alert = await screen.findByText("Couldn't save the project")
      expect(alert.closest('[role="alert"]')).toHaveTextContent(
        'A review of this project is still running. Wait for it to finish, then try again.',
      )
      expect(onSaved).not.toHaveBeenCalled()
    })
  })
})
