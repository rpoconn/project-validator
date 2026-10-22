import { PencilIcon, Trash2Icon } from 'lucide-react'
import { useId, useState } from 'react'

import { errorMessage, isApiError } from '@/api/errors'
import type { ProjectRead, TimelineItem } from '@/api/generated/types.gen'
import { useDeleteProject, useProject } from '@/api/projects'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'

import { formatBudgetRange, formatDate, formatDueDate } from './format'
import { ReviewPanel } from './ReviewPanel'

interface ProjectDetailProps {
  projectId: number
  onEdit: (project: ProjectRead) => void
  onDeleted: () => void
}

export function ProjectDetail({ projectId, onEdit, onDeleted }: ProjectDetailProps) {
  const { data: project, error, isPending, isError, isFetching, refetch } = useProject(projectId)
  const deleteProject = useDeleteProject()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const headingId = useId()

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-muted-foreground">
        <Spinner aria-hidden="true" />
        <span role="status">Loading project…</span>
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

  if (isApiError(error, 404)) {
    return <ErrorBanner title="Project not found" message={errorMessage(error)} />
  }

  if (!project) return loadFailure("Couldn't load the project")

  return (
    <article aria-labelledby={headingId} className="flex flex-col gap-4">
      {/* A failed background refresh (e.g. while polling a review) keeps the last data shown. */}
      {isError && loadFailure("Couldn't refresh the project")}
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 id={headingId} className="text-lg break-words">
              {project.title}
            </h2>
          </CardTitle>
          <CardDescription className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{project.industry}</Badge>
            <span>Created {formatDate(project.created_at)}</span>
          </CardDescription>
          <CardAction className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              // Edits start a new review, so they wait for the running one to finish.
              disabled={project.review_status === 'pending'}
              title={
                project.review_status === 'pending'
                  ? 'Available once the review finishes'
                  : undefined
              }
              onClick={() => onEdit(project)}
            >
              <PencilIcon data-icon="inline-start" />
              Edit
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                deleteProject.reset()
                setConfirmDelete(true)
              }}
            >
              <Trash2Icon data-icon="inline-start" />
              Delete
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl className="grid gap-1">
            <dt className="text-xs font-medium text-muted-foreground uppercase">Budget</dt>
            <dd>{formatBudgetRange(project.budget_min, project.budget_max)}</dd>
          </dl>
          <p className="break-words whitespace-pre-wrap">{project.description}</p>
          <Separator />
          <Timeline items={project.timeline} />
        </CardContent>
      </Card>
      <ReviewPanel project={project} />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete “${project.title}”?`}
        description={
          deleteProject.isError ? (
            <span role="alert" className="text-destructive">
              Couldn't delete the project: {errorMessage(deleteProject.error)}
            </span>
          ) : (
            'This permanently removes the project and its AI review. It cannot be undone.'
          )
        }
        cancelLabel="Keep project"
        confirmLabel={deleteProject.isError ? 'Try again' : 'Delete project'}
        destructive
        pending={deleteProject.isPending}
        onConfirm={() =>
          deleteProject.mutate(project.id, {
            onSuccess: () => {
              setConfirmDelete(false)
              onDeleted()
            },
          })
        }
      />
    </article>
  )
}

function Timeline({ items }: { items: TimelineItem[] }) {
  const sorted = [...items].sort((a, b) => a.due_at.localeCompare(b.due_at))
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3 id={headingId} className="font-medium">
        Timeline
      </h3>
      {sorted.length === 0 ? (
        <p className="text-muted-foreground">No timeline entries</p>
      ) : (
        <ol aria-label="Milestones" className="flex flex-col gap-2">
          {sorted.map((item, index) => (
            <li key={index} className="flex items-baseline justify-between gap-4">
              <span className="break-words">{item.goal}</span>
              <time dateTime={item.due_at} className="shrink-0 text-sm text-muted-foreground">
                {formatDueDate(item.due_at)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
