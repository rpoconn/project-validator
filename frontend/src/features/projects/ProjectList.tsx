import { FolderKanbanIcon, PlusIcon } from 'lucide-react'

import { errorMessage } from '@/api/errors'
import type { ProjectRead } from '@/api/generated/types.gen'
import { useProjects } from '@/api/projects'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'

import { ProjectListItem } from './ProjectListItem'

interface ProjectListProps {
  selectedId: number | null
  onSelect: (projectId: number) => void
  onCreate: () => void
}

export function ProjectList({ selectedId, onSelect, onCreate }: ProjectListProps) {
  const { data: projects, error, isPending, isError, isFetching, refetch } = useProjects()

  if (isPending) {
    return (
      <div aria-busy="true" aria-label="Loading projects" className="flex flex-col gap-2">
        {[0, 1, 2].map((key) => (
          <Skeleton key={key} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  const loadFailure = (title: string) => (
    <ErrorBanner
      title={title}
      message={errorMessage(error)}
      onRetry={() => void refetch()}
      retrying={isFetching}
    />
  )

  if (!projects) return loadFailure("Couldn't load projects")

  // A failed background refresh keeps the last projects on screen beneath the error.
  return (
    <div className="flex flex-col gap-2">
      {isError && loadFailure("Couldn't refresh projects")}
      <ProjectListContent
        projects={projects}
        selectedId={selectedId}
        onSelect={onSelect}
        onCreate={onCreate}
      />
    </div>
  )
}

function ProjectListContent({
  projects,
  selectedId,
  onSelect,
  onCreate,
}: ProjectListProps & { projects: ProjectRead[] }) {
  if (projects.length === 0) {
    return (
      <Empty className="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FolderKanbanIcon />
          </EmptyMedia>
          <EmptyTitle>No projects yet</EmptyTitle>
          <EmptyDescription>
            Add a project to get an AI review against the rest of your portfolio.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={onCreate}>
            <PlusIcon data-icon="inline-start" />
            Create your first project
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  return (
    <ul aria-label="Projects" className="flex flex-col gap-2">
      {projects.map((project) => (
        <li key={project.id}>
          <ProjectListItem
            project={project}
            selected={project.id === selectedId}
            onSelect={onSelect}
          />
        </li>
      ))}
    </ul>
  )
}
