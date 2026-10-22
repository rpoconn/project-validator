import { CircleAlertIcon, RotateCcwIcon, SparklesIcon, TriangleAlertIcon } from 'lucide-react'
import { type ReactElement, useId } from 'react'

import { errorMessage } from '@/api/errors'
import type { ProjectRead, ReviewStatus } from '@/api/generated/types.gen'
import { useRerunReview } from '@/api/projects'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { Spinner } from '@/components/ui/spinner'

import { formatDateTime } from './format'

const runLabel: Record<Exclude<ReviewStatus, 'pending'>, string> = {
  unreviewed: 'Run review',
  error: 'Retry review',
  complete: 'Re-run review',
}

export function ReviewPanel({ project }: { project: ProjectRead }) {
  const rerun = useRerunReview()
  const status = project.review_status

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <SparklesIcon className="size-4" aria-hidden="true" />
          <h2>AI risk review</h2>
        </CardTitle>
        {project.review_updated_at && status !== 'pending' && (
          <CardDescription>Updated {formatDateTime(project.review_updated_at)}</CardDescription>
        )}
        {status !== 'pending' && (
          <CardAction>
            <Button
              size="sm"
              variant={status === 'complete' ? 'outline' : 'default'}
              disabled={rerun.isPending}
              onClick={() => rerun.mutate(project.id)}
            >
              {rerun.isPending ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : (
                <RotateCcwIcon data-icon="inline-start" />
              )}
              {runLabel[status]}
            </Button>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {rerun.isError && (
          <ErrorBanner title="Couldn't start the review" message={errorMessage(rerun.error)} />
        )}
        <ReviewBody project={project} />
      </CardContent>
    </Card>
  )
}

function ReviewBody({ project }: { project: ProjectRead }): ReactElement {
  switch (project.review_status) {
    case 'pending':
      return (
        <div role="status" className="flex flex-col gap-1">
          <p className="flex items-center gap-2 font-medium">
            <Spinner aria-hidden="true" />
            Analyzing project…
          </p>
          <p className="text-muted-foreground">
            Claude is comparing it with your other projects. This usually takes 10–30 seconds.
          </p>
        </div>
      )
    case 'unreviewed':
      return (
        <Alert>
          <TriangleAlertIcon />
          <AlertTitle>Review was interrupted</AlertTitle>
          <AlertDescription>
            The server restarted before this review finished. Run it again to get a result.
          </AlertDescription>
        </Alert>
      )
    case 'error':
      return (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>Review failed</AlertTitle>
          <AlertDescription>
            <pre className="font-mono text-xs break-words whitespace-pre-wrap">
              {project.review_error ?? 'No error details were recorded.'}
            </pre>
          </AlertDescription>
        </Alert>
      )
    case 'complete':
      return project.review ? (
        <CompletedReview review={project.review} />
      ) : (
        <p className="text-muted-foreground">The review finished but returned no data.</p>
      )
  }
}

function CompletedReview({ review }: { review: NonNullable<ProjectRead['review']> }) {
  const risksHeadingId = useId()
  return (
    <>
      <p>{review.summary}</p>
      <ul aria-label="Tags" className="flex flex-wrap gap-2">
        {review.tags.map((tag) => (
          <li key={tag}>
            <Badge variant="secondary">{tag}</Badge>
          </li>
        ))}
      </ul>
      <section aria-labelledby={risksHeadingId} className="flex flex-col gap-2">
        <h3 id={risksHeadingId} className="font-medium">
          Risks
        </h3>
        {review.risks.length > 0 ? (
          <ul className="flex list-disc flex-col gap-1 pl-5">
            {review.risks.map((risk, index) => (
              <li key={index}>{risk}</li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No risks identified.</p>
        )}
      </section>
    </>
  )
}
