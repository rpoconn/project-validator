import type { ProjectRead } from '@/api/generated/types.gen'
import { cn } from '@/lib/utils'

import { formatBudgetRange } from './format'
import { ReviewStatusBadge } from './ReviewStatusBadge'

interface ProjectListItemProps {
  project: ProjectRead
  selected: boolean
  onSelect: (projectId: number) => void
}

export function ProjectListItem({ project, selected, onSelect }: ProjectListItemProps) {
  return (
    <button
      type="button"
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelect(project.id)}
      className={cn(
        'flex w-full flex-col gap-1 rounded-lg border p-3 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
        selected && 'border-primary/40 bg-muted',
      )}
    >
      <span className="flex items-start justify-between gap-2">
        <span className="font-medium break-words">{project.title}</span>
        <ReviewStatusBadge status={project.review_status} />
      </span>
      <span className="text-xs text-muted-foreground">
        {project.industry} · {formatBudgetRange(project.budget_min, project.budget_max)}
      </span>
    </button>
  )
}
