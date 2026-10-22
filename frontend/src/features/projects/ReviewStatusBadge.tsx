import type { ComponentProps } from 'react'

import type { ReviewStatus } from '@/api/generated/types.gen'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'

const appearance: Record<
  ReviewStatus,
  { label: string; variant: ComponentProps<typeof Badge>['variant'] }
> = {
  unreviewed: { label: 'Not reviewed', variant: 'outline' },
  pending: { label: 'Reviewing', variant: 'secondary' },
  complete: { label: 'Reviewed', variant: 'default' },
  error: { label: 'Review failed', variant: 'destructive' },
}

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const { label, variant } = appearance[status]
  return (
    <Badge variant={variant}>
      {status === 'pending' && <Spinner data-icon="inline-start" aria-hidden="true" />}
      {label}
    </Badge>
  )
}
