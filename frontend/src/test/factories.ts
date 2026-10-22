import type { ProjectRead, ProjectReview } from '@/api/generated/types.gen'

export function makeReview(overrides: Partial<ProjectReview> = {}): ProjectReview {
  return {
    summary: 'A clinic booking rebuild with a tight timeline.',
    tags: ['Healthcare', 'Scheduling', 'Web'],
    risks: ['Overlaps with the patient portal project', 'Beta is due before design sign-off'],
    ...overrides,
  }
}

let nextId = 1

export function makeProject(overrides: Partial<ProjectRead> = {}): ProjectRead {
  const id = overrides.id ?? nextId++
  return {
    id,
    title: `Project ${id}`,
    description: 'Rebuild the booking flow.',
    budget_min: 10000,
    budget_max: 25000,
    industry: 'Healthcare',
    timeline: [],
    created_at: '2026-10-20T12:00:00Z',
    review_status: 'complete',
    review: makeReview(),
    review_error: null,
    review_updated_at: '2026-10-20T12:00:30Z',
    ...overrides,
  }
}
