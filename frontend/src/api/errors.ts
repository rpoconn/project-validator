import { client } from './generated/client.gen'
import { zHttpValidationError } from './generated/zod.gen'

/** A non-2xx response from the API. `body` is the parsed JSON (or text) the server sent. */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown) {
    super(describeBody(status, body))
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

function describeBody(status: number, body: unknown): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const { detail } = body
    if (typeof detail === 'string' && detail.trim() !== '') return detail
  }
  return `Request failed with status ${status}`
}

/**
 * The generated client throws the bare response body, which loses the status code. Wrapping it
 * lets callers tell a 409 or 422 apart from other failures. Network failures have no response
 * and are passed through unchanged.
 */
export function toApiError(error: unknown, response: Response | undefined): unknown {
  return response ? new ApiError(response.status, error) : error
}

if (!client.interceptors.error.exists(toApiError)) {
  client.interceptors.error.use(toApiError)
}

export function isApiError(error: unknown, status?: number): error is ApiError {
  return error instanceof ApiError && (status === undefined || error.status === status)
}

/** A user-facing message for any error thrown by an API call. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof TypeError)
    return 'Could not reach the server. Check that the backend is running.'
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong'
}

export interface ValidationIssue {
  /** Dotted path into the request body (e.g. `timeline.0.goal`); empty for body-level errors. */
  path: string
  message: string
}

/** The field errors from a FastAPI 422 response, or `[]` for any other error. */
export function validationIssues(error: unknown): ValidationIssue[] {
  if (!isApiError(error, 422)) return []
  const parsed = zHttpValidationError.safeParse(error.body)
  if (!parsed.success) return []
  return (parsed.data.detail ?? []).map(({ loc, msg }) => ({
    path: (loc[0] === 'body' ? loc.slice(1) : loc).join('.'),
    // Pydantic prefixes errors raised from custom validators.
    message: msg.replace(/^Value error, /, ''),
  }))
}
