import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/server'

import { ApiError, errorMessage, isApiError, validationIssues } from './errors'
import { rerunReview } from './generated/sdk.gen'

describe('ApiError', () => {
  it('uses a string detail as its message', () => {
    expect(new ApiError(409, { detail: 'Already running' }).message).toBe('Already running')
  })

  it('falls back to the status code', () => {
    expect(new ApiError(500, 'Internal Server Error').message).toBe(
      'Request failed with status 500',
    )
  })

  it('is what the generated client throws for non-2xx responses', async () => {
    server.use(
      http.post('*/api/projects/:id/review', () =>
        HttpResponse.json(
          { detail: 'Project 1 already has a review in progress' },
          { status: 409 },
        ),
      ),
    )

    const error: unknown = await rerunReview({ path: { project_id: 1 }, throwOnError: true }).catch(
      (thrown: unknown) => thrown,
    )

    expect(isApiError(error, 409)).toBe(true)
    expect(errorMessage(error)).toBe('Project 1 already has a review in progress')
  })
})

describe('errorMessage', () => {
  it('explains network failures', () => {
    expect(errorMessage(new TypeError('Failed to fetch'))).toMatch(/Could not reach the server/)
  })

  it('has a fallback for unknown values', () => {
    expect(errorMessage(undefined)).toBe('Something went wrong')
  })
})

describe('validationIssues', () => {
  it('turns a FastAPI 422 into body-relative paths', () => {
    const error = new ApiError(422, {
      detail: [
        { loc: ['body', 'title'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'timeline', 0, 'goal'], msg: 'Too long', type: 'string_too_long' },
        {
          loc: ['body'],
          msg: 'Value error, budget_max must be >= budget_min',
          type: 'value_error',
        },
      ],
    })

    expect(validationIssues(error)).toEqual([
      { path: 'title', message: 'Field required' },
      { path: 'timeline.0.goal', message: 'Too long' },
      { path: '', message: 'budget_max must be >= budget_min' },
    ])
  })

  it('ignores other errors and malformed bodies', () => {
    expect(validationIssues(new ApiError(500, { detail: [] }))).toEqual([])
    expect(validationIssues(new ApiError(422, { detail: 'nope' }))).toEqual([])
    expect(validationIssues(new Error('x'))).toEqual([])
  })
})
