import { useId } from 'react'

import { errorMessage, isApiError } from '@/api/errors'
import type { TimelineItem } from '@/api/generated/types.gen'
import { useProject } from '@/api/projects'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'

import { formatBudgetRange, formatDate, formatDueDate } from './format'
import { ReviewPanel } from './ReviewPanel'

export function ProjectDetail({ projectId }: { projectId: number }) {
  const { data: project, error, isPending, isError, isFetching, refetch } = useProject(projectId)
  const headingId = useId()

  if (isPending) {
    return (
      <div className="flex items-center justify-center gap-2 p-8 text-muted-foreground">
        <Spinner aria-hidden="true" />
        <span role="status">Loading project…</span>
      </div>
    )
  }

  if (isError) {
    return isApiError(error, 404) ? (
      <ErrorBanner title="Project not found" message={errorMessage(error)} />
    ) : (
      <ErrorBanner
        title="Couldn't load the project"
        message={errorMessage(error)}
        onRetry={() => void refetch()}
        retrying={isFetching}
      />
    )
  }

  return (
    <article aria-labelledby={headingId} className="flex flex-col gap-4">
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
