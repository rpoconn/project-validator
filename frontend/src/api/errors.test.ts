import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '@/test/server'

import { ApiError, errorMessage, isApiError, toApiError, validationIssues } from './errors'
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

  it.each([
    ['blank detail', { detail: '   ' }],
    ['non-string detail', { detail: [{ loc: ['body'], msg: 'x' }] }],
    ['no detail', { error: 'x' }],
    ['null body', null],
  ])('falls back to the status code for a %s', (_label, body) => {
    expect(new ApiError(422, body).message).toBe('Request failed with status 422')
  })

  it('keeps the status and body and is named', () => {
    const body = { detail: 'Nope' }
    const error = new ApiError(404, body)

    expect(error.name).toBe('ApiError')
    expect(error.status).toBe(404)
    expect(error.body).toBe(body)
    expect(error).toBeInstanceOf(Error)
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

describe('toApiError', () => {
  it('wraps a response body with its status', () => {
    const wrapped = toApiError({ detail: 'Gone' }, new Response(null, { status: 410 }))

    expect(isApiError(wrapped, 410)).toBe(true)
    expect(errorMessage(wrapped)).toBe('Gone')
  })

  it('passes network failures through unchanged', () => {
    const failure = new TypeError('Failed to fetch')

    expect(toApiError(failure, undefined)).toBe(failure)
  })
})

describe('isApiError', () => {
  it('matches any status when none is given', () => {
    expect(isApiError(new ApiError(500, null))).toBe(true)
    expect(isApiError(new ApiError(500, null), 404)).toBe(false)
  })

  it('rejects other values', () => {
    expect(isApiError(new Error('x'))).toBe(false)
    expect(isApiError({ status: 500 })).toBe(false)
    expect(isApiError(null)).toBe(false)
  })
})

describe('errorMessage', () => {
  it('explains network failures', () => {
    expect(errorMessage(new TypeError('Failed to fetch'))).toMatch(/Could not reach the server/)
  })

  it('uses a plain error message when there is one', () => {
    expect(errorMessage(new Error('Disk full'))).toBe('Disk full')
    expect(errorMessage(new Error(''))).toBe('Something went wrong')
  })

  it('has a fallback for unknown values', () => {
    expect(errorMessage(undefined)).toBe('Something went wrong')
    expect(errorMessage('a string')).toBe('Something went wrong')
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

  it('keeps locations that are not under the body', () => {
    const error = new ApiError(422, {
      detail: [
        { loc: ['path', 'project_id'], msg: 'Value error, not an integer', type: 'int_parsing' },
      ],
    })

    expect(validationIssues(error)).toEqual([
      { path: 'path.project_id', message: 'not an integer' },
    ])
  })

  it('returns nothing when the 422 has no detail list', () => {
    expect(validationIssues(new ApiError(422, {}))).toEqual([])
  })

  it('ignores other errors and malformed bodies', () => {
    expect(validationIssues(new ApiError(500, { detail: [] }))).toEqual([])
    expect(validationIssues(new ApiError(422, { detail: 'nope' }))).toEqual([])
    expect(validationIssues(new Error('x'))).toEqual([])
  })
})
