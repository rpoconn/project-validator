import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useEffect } from 'react'

import { isApiError } from './errors'
import { getProjectOptions, listProjectsOptions } from './generated/@tanstack/react-query.gen'
import { createProject, rerunReview } from './generated/sdk.gen'
import type { ProjectCreate, ProjectRead } from './generated/types.gen'

/** How often a project is refetched while its review is pending. */
export const REVIEW_POLL_INTERVAL_MS = 2000

const projectOptions = (projectId: number) => getProjectOptions({ path: { project_id: projectId } })

const isPending = (project: ProjectRead): boolean => project.review_status === 'pending'

/** Write a project into both the detail cache and its row in the list cache. */
function storeProject(queryClient: QueryClient, project: ProjectRead): void {
  queryClient.setQueryData(projectOptions(project.id).queryKey, project)
  queryClient.setQueryData(listProjectsOptions().queryKey, (projects) =>
    projects?.map((existing) => (existing.id === project.id ? project : existing)),
  )
}

export function useProjects(): UseQueryResult<ProjectRead[]> {
  return useQuery({
    ...listProjectsOptions(),
    // Keeps status badges current for reviews running on projects that aren't selected.
    refetchInterval: (query) =>
      query.state.data?.some(isPending) ? REVIEW_POLL_INTERVAL_MS * 2 : false,
  })
}

/** A single project, polled while its review is pending. */
export function useProject(projectId: number): UseQueryResult<ProjectRead, unknown> {
  const queryClient = useQueryClient()
  const query = useQuery({
    ...projectOptions(projectId),
    placeholderData: () =>
      queryClient
        .getQueryData(listProjectsOptions().queryKey)
        ?.find((project) => project.id === projectId),
    refetchInterval: (query) =>
      query.state.data && isPending(query.state.data) ? REVIEW_POLL_INTERVAL_MS : false,
  })

  const { data, isPlaceholderData } = query
  useEffect(() => {
    if (data && !isPlaceholderData) storeProject(queryClient, data)
  }, [data, isPlaceholderData, queryClient])

  return query
}

export function useCreateProject(): UseMutationResult<ProjectRead, Error, ProjectCreate> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ProjectCreate) =>
      (await createProject({ body, throwOnError: true })).data,
    onSuccess: (project) => {
      queryClient.setQueryData(projectOptions(project.id).queryKey, project)
      queryClient.setQueryData(listProjectsOptions().queryKey, (projects) =>
        projects ? [project, ...projects] : projects,
      )
      void queryClient.invalidateQueries({ queryKey: listProjectsOptions().queryKey })
    },
  })
}

/**
 * Start a fresh review. A 409 means a review is already running, so it resolves with the
 * project's current state instead of failing.
 */
export function useRerunReview(): UseMutationResult<ProjectRead, Error, number> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (projectId: number) => {
      try {
        return (await rerunReview({ path: { project_id: projectId }, throwOnError: true })).data
      } catch (error) {
        if (isApiError(error, 409)) {
          return queryClient.fetchQuery({ ...projectOptions(projectId), staleTime: 0 })
        }
        throw error
      }
    },
    onSuccess: (project) => storeProject(queryClient, project),
  })
}
