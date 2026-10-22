import { describe, expect, it } from 'vitest'

import { makeProject } from '@/test/factories'

import {
  emptyProjectForm,
  type ProjectFormInput,
  projectFormErrorMap,
  projectFormSchema,
  toProjectFormInput,
} from './projectForm.schema'

const validInput: ProjectFormInput = {
  title: '  Clinic scheduling  ',
  description: 'Rebuild the booking flow.',
  industry: 'Healthcare',
  budget_min: '10000',
  budget_max: '25000',
  timeline: [{ goal: ' Beta ', due_at: '2026-12-01' }],
}

function errorsFor(input: ProjectFormInput): Record<string, string> {
  const result = projectFormSchema.safeParse(input, { error: projectFormErrorMap })
  if (result.success) return {}
  return Object.fromEntries(
    result.error.issues.map((issue) => [issue.path.join('.'), issue.message]),
  )
}

describe('projectFormSchema', () => {
  it('produces an API payload: trimmed text, numeric budgets, UTC due dates', () => {
    expect(projectFormSchema.parse(validInput)).toEqual({
      title: 'Clinic scheduling',
      description: 'Rebuild the booking flow.',
      industry: 'Healthcare',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00.000Z' }],
    })
  })

  it('turns an existing project into form input that parses back to the same payload', () => {
    const project = makeProject({
      title: 'Clinic scheduling',
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00Z' }],
    })

    const input = toProjectFormInput(project)

    expect(input).toEqual({
      title: 'Clinic scheduling',
      description: project.description,
      industry: project.industry,
      budget_min: '10000',
      budget_max: '25000',
      timeline: [{ goal: 'Beta', due_at: '2026-12-01' }],
    })
    expect(projectFormSchema.parse(input)).toEqual({
      title: 'Clinic scheduling',
      description: project.description,
      industry: project.industry,
      budget_min: 10000,
      budget_max: 25000,
      timeline: [{ goal: 'Beta', due_at: '2026-12-01T00:00:00.000Z' }],
    })
  })

  it('reports every required field on an empty form', () => {
    expect(errorsFor(emptyProjectForm)).toEqual({
      title: 'Required',
      description: 'Required',
      industry: 'Required',
      budget_min: 'Required',
      budget_max: 'Required',
    })
  })

  it('treats whitespace-only text as missing', () => {
    expect(errorsFor({ ...validInput, title: '   ' })).toEqual({ title: 'Required' })
  })

  it('rejects a maximum budget below the minimum', () => {
    expect(errorsFor({ ...validInput, budget_min: '500', budget_max: '100' })).toEqual({
      budget_max: 'Maximum budget must be at least the minimum',
    })
  })

  it('checks the budget range alongside other field errors', () => {
    expect(errorsFor({ ...validInput, title: '', budget_min: '500', budget_max: '100' })).toEqual({
      title: 'Required',
      budget_max: 'Maximum budget must be at least the minimum',
    })
  })

  it('skips the range check until both budgets are valid', () => {
    expect(errorsFor({ ...validInput, budget_min: '-1', budget_max: '' })).toEqual({
      budget_min: 'Must be 0 or more',
      budget_max: 'Required',
    })
  })

  it('rejects fractional budgets', () => {
    expect(errorsFor({ ...validInput, budget_min: '1.5' })).toEqual({
      budget_min: 'Enter a whole number',
    })
  })

  it('enforces the API length limits', () => {
    expect(errorsFor({ ...validInput, title: 'x'.repeat(201) })).toEqual({
      title: 'Must be 200 characters or fewer',
    })
  })

  it('validates each timeline entry', () => {
    expect(errorsFor({ ...validInput, timeline: [{ goal: '', due_at: '' }] })).toEqual({
      'timeline.0.goal': 'Required',
      'timeline.0.due_at': 'Choose a date',
    })
  })

  it('caps the number of timeline entries', () => {
    const timeline = Array.from({ length: 51 }, () => ({ goal: 'Step', due_at: '2026-12-01' }))
    expect(errorsFor({ ...validInput, timeline })).toEqual({
      timeline: 'No more than 50 entries',
    })
  })
})
