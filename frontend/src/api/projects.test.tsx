import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { makeProject } from '@/test/factories'
import { server } from '@/test/server'

import { getProjectQueryKey, listProjectsQueryKey } from './generated/@tanstack/react-query.gen'
import type { ProjectCreate, ProjectRead } from './generated/types.gen'
import {
  REVIEW_POLL_INTERVAL_MS,
  useCreateProject,
  useDeleteProject,
  useProject,
  useProjects,
  useRerunReview,
  useUpdateProject,
} from './projects'

const listKey = listProjectsQueryKey()
const detailKey = (id: number) => getProjectQueryKey({ path: { project_id: id } })

function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

const body: ProjectCreate = {
  title: 'New',
  description: 'd',
  budget_min: 1,
  budget_max: 2,
  industry: 'i',
  timeline: [],
}

describe('useProject', () => {
  it('serves the list entry as a placeholder, then writes the fetched project back', async () => {
    const stale = makeProject({ title: 'Stale title' })
    const fresh = { ...stale, title: 'Fresh title' }
    server.use(http.get(`*/api/projects/${stale.id}`, () => HttpResponse.json(fresh)))
    const queryClient = createClient()
    queryClient.setQueryData(listKey, [stale])

    const { result } = renderHook(() => useProject(stale.id), { wrapper: wrapperFor(queryClient) })

    expect(result.current.isPlaceholderData).toBe(true)
    expect(result.current.data?.title).toBe('Stale title')
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(false))
    expect(result.current.data?.title).toBe('Fresh title')
    await waitFor(() => expect(queryClient.getQueryData<ProjectRead[]>(listKey)).toEqual([fresh]))
  })
})

describe('polling', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('useProject refetches only while the review is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const pending = makeProject({ review_status: 'pending', review: null })
    const complete = { ...pending, review_status: 'complete' as const }
    let calls = 0
    server.use(
      http.get(`*/api/projects/${pending.id}`, () => {
        calls += 1
        return HttpResponse.json(calls < 3 ? pending : complete)
      }),
    )

    const { result } = renderHook(() => useProject(pending.id), {
      wrapper: wrapperFor(createClient()),
    })

    await waitFor(() => expect(calls).toBe(1))
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    await waitFor(() => expect(calls).toBe(2))
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    await waitFor(() => expect(result.current.data?.review_status).toBe('complete'))
    expect(calls).toBe(3)

    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS * 3)
    expect(calls).toBe(3)
  })

  it('useProjects polls at a slower rate while any project is pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const pending = makeProject({ review_status: 'pending', review: null })
    const done = makeProject()
    let calls = 0
    server.use(
      http.get('*/api/projects', () => {
        calls += 1
        return HttpResponse.json(
          calls < 2 ? [pending, done] : [{ ...pending, review_status: 'complete' }, done],
        )
      }),
    )

    const { result } = renderHook(() => useProjects(), { wrapper: wrapperFor(createClient()) })

    await waitFor(() => expect(calls).toBe(1))
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    expect(calls).toBe(1)
    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS)
    await waitFor(() => expect(calls).toBe(2))
    await waitFor(() => expect(result.current.data?.[0]?.review_status).toBe('complete'))

    await vi.advanceTimersByTimeAsync(REVIEW_POLL_INTERVAL_MS * 4)
    expect(calls).toBe(2)
  })
})

describe('useCreateProject', () => {
  it('prepends the new project to the list and caches its detail', async () => {
    const existing = makeProject()
    const created = makeProject({ title: 'New', review_status: 'pending', review: null })
    server.use(
      http.post('*/api/projects', () => HttpResponse.json(created, { status: 201 })),
      http.get('*/api/projects', () => HttpResponse.json([created, existing])),
    )
    const queryClient = createClient()
    queryClient.setQueryData(listKey, [existing])

    const { result } = renderHook(() => useCreateProject(), { wrapper: wrapperFor(queryClient) })
    await act(() => result.current.mutateAsync(body))

    expect(queryClient.getQueryData(detailKey(created.id))).toEqual(created)
    expect(queryClient.getQueryData<ProjectRead[]>(listKey)?.map((p) => p.id)).toEqual([
      created.id,
      existing.id,
    ])
  })

  it('leaves the list cache alone when the list was never loaded', async () => {
    const created = makeProject()
    server.use(
      http.post('*/api/projects', () => HttpResponse.json(created, { status: 201 })),
      http.get('*/api/projects', () => HttpResponse.json([created])),
    )
    const queryClient = createClient()

    const { result } = renderHook(() => useCreateProject(), { wrapper: wrapperFor(queryClient) })
    await act(() => result.current.mutateAsync(body))

    expect(queryClient.getQueryData(listKey)).toBeUndefined()
  })
})

describe('useUpdateProject', () => {
  it('writes the updated project into both caches', async () => {
    const before = makeProject({ title: 'Before' })
    const other = makeProject()
    const after = { ...before, title: 'After' }
    server.use(http.put(`*/api/projects/${before.id}`, () => HttpResponse.json(after)))
    const queryClient = createClient()
    queryClient.setQueryData(listKey, [other, before])
    queryClient.setQueryData(detailKey(before.id), before)

    const { result } = renderHook(() => useUpdateProject(), { wrapper: wrapperFor(queryClient) })
    await act(() => result.current.mutateAsync({ projectId: before.id, body }))

    expect(queryClient.getQueryData(detailKey(before.id))).toEqual(after)
    expect(queryClient.getQueryData<ProjectRead[]>(listKey)).toEqual([other, after])
  })
})

describe('useDeleteProject', () => {
  it('drops the project from both caches', async () => {
    const doomed = makeProject()
    const other = makeProject()
    server.use(
      http.delete(`*/api/projects/${doomed.id}`, () => new HttpResponse(null, { status: 204 })),
      http.get('*/api/projects', () => HttpResponse.json([other])),
    )
    const queryClient = createClient()
    queryClient.setQueryData(listKey, [doomed, other])
    queryClient.setQueryData(detailKey(doomed.id), doomed)

    const { result } = renderHook(() => useDeleteProject(), { wrapper: wrapperFor(queryClient) })
    await act(() => result.current.mutateAsync(doomed.id))

    expect(queryClient.getQueryData(detailKey(doomed.id))).toBeUndefined()
    expect(queryClient.getQueryData<ProjectRead[]>(listKey)).toEqual([other])
  })
})

describe('useRerunReview', () => {
  it('stores the pending project the server returns', async () => {
    const project = makeProject()
    const pending = { ...project, review_status: 'pending' as const, review: null }
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json(pending, { status: 202 }),
      ),
    )
    const queryClient = createClient()
    queryClient.setQueryData(listKey, [project])

    const { result } = renderHook(() => useRerunReview(), { wrapper: wrapperFor(queryClient) })
    const returned = await act(() => result.current.mutateAsync(project.id))

    expect(returned).toEqual(pending)
    expect(queryClient.getQueryData(detailKey(project.id))).toEqual(pending)
    expect(queryClient.getQueryData<ProjectRead[]>(listKey)).toEqual([pending])
  })

  it('falls back to fetching the project when a review is already running', async () => {
    const project = makeProject()
    const pending = { ...project, review_status: 'pending' as const, review: null }
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json({ detail: 'already running' }, { status: 409 }),
      ),
      http.get(`*/api/projects/${project.id}`, () => HttpResponse.json(pending)),
    )
    const queryClient = createClient()

    const { result } = renderHook(() => useRerunReview(), { wrapper: wrapperFor(queryClient) })
    const returned = await act(() => result.current.mutateAsync(project.id))

    expect(returned).toEqual(pending)
    expect(queryClient.getQueryData(detailKey(project.id))).toEqual(pending)
  })

  it('rethrows other failures', async () => {
    const project = makeProject()
    server.use(
      http.post(`*/api/projects/${project.id}/review`, () =>
        HttpResponse.json({ detail: 'Project not found' }, { status: 404 }),
      ),
    )
    const queryClient = createClient()

    const { result } = renderHook(() => useRerunReview(), { wrapper: wrapperFor(queryClient) })

    await expect(act(() => result.current.mutateAsync(project.id))).rejects.toThrow(
      'Project not found',
    )
    expect(queryClient.getQueryData(detailKey(project.id))).toBeUndefined()
  })
})
