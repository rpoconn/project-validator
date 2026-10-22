import { z } from 'zod'

import { zProjectCreate, zTimelineItem } from '../../api/generated/zod.gen'

// Field rules come from the generated (backend-derived) schemas; this file only adapts raw input
// values to them and adds the cross-field budget check.
const api = zProjectCreate.shape

const text = <T extends z.ZodType<string, string>>(rule: T) => z.string().trim().pipe(rule)

/** Number inputs hold strings; blank stays a "required" error rather than becoming 0. */
const budget = <T extends z.ZodType<number, number>>(rule: T) =>
  z.string().trim().min(1).transform(Number).pipe(rule)

/** `<input type="date">` value (YYYY-MM-DD) → midnight UTC, the format the API expects. */
const dueDate = z.iso
  .date()
  .transform((date) => new Date(`${date}T00:00:00Z`).toISOString())
  .pipe(zTimelineItem.shape.due_at)

const BUDGET_FIELDS: ReadonlyArray<PropertyKey | undefined> = ['budget_min', 'budget_max']

export const projectFormSchema = z
  .object({
    title: text(api.title),
    description: text(api.description),
    industry: text(api.industry),
    budget_min: budget(api.budget_min),
    budget_max: budget(api.budget_max),
    timeline: z
      .array(z.object({ goal: text(zTimelineItem.shape.goal), due_at: dueDate }))
      .pipe(api.timeline.unwrap()),
  })
  .refine(({ budget_min, budget_max }) => budget_max >= budget_min, {
    path: ['budget_max'],
    message: 'Maximum budget must be at least the minimum',
    // Check the range alongside other field errors, but only once both budgets are valid numbers.
    when: ({ issues }) => !issues.some(({ path }) => BUDGET_FIELDS.includes(path?.[0])),
  })

export type ProjectFormInput = z.input<typeof projectFormSchema>
export type ProjectFormOutput = z.output<typeof projectFormSchema>

export const emptyProjectForm: ProjectFormInput = {
  title: '',
  description: '',
  industry: '',
  budget_min: '',
  budget_max: '',
  timeline: [],
}

export const emptyTimelineItem: ProjectFormInput['timeline'][number] = { goal: '', due_at: '' }

/** Friendly messages for the generated schemas' built-in checks. */
export const projectFormErrorMap: z.core.$ZodErrorMap = (issue) => {
  switch (issue.code) {
    case 'too_small':
      if (issue.origin === 'string') {
        return issue.minimum === 1 ? 'Required' : `Must be at least ${issue.minimum} characters`
      }
      return issue.origin === 'array' ? undefined : `Must be ${issue.minimum} or more`
    case 'too_big':
      if (issue.origin === 'string') return `Must be ${issue.maximum} characters or fewer`
      if (issue.origin === 'array') return `No more than ${issue.maximum} entries`
      return `Must be ${issue.maximum} or less`
    case 'invalid_type':
      return issue.expected === 'int' || issue.expected === 'number'
        ? 'Enter a whole number'
        : undefined
    case 'invalid_format':
      return issue.format === 'date' ? 'Choose a date' : undefined
    default:
      return undefined
  }
}
