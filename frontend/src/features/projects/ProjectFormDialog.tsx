import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlertIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { type ReactNode, useId } from 'react'
import { type FieldPath, useFieldArray, useForm, type UseFormSetError } from 'react-hook-form'

import { errorMessage, validationIssues } from '@/api/errors'
import type { ProjectRead } from '@/api/generated/types.gen'
import { useCreateProject } from '@/api/projects'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'

import {
  emptyProjectForm,
  emptyTimelineItem,
  type ProjectFormInput,
  type ProjectFormOutput,
  projectFormErrorMap,
  projectFormSchema,
} from './projectForm.schema'

const INDUSTRY_SUGGESTIONS = [
  'Technology',
  'Healthcare',
  'Finance',
  'Retail',
  'Manufacturing',
  'Education',
  'Energy',
  'Logistics',
  'Media',
  'Government',
  'Real estate',
  'Hospitality',
]

interface ProjectFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (project: ProjectRead) => void
}

export function ProjectFormDialog({ open, onOpenChange, onCreated }: ProjectFormDialogProps) {
  const createProject = useCreateProject()

  return (
    <Dialog
      open={open}
      // Stay open while saving so the result (or a validation error) isn't lost.
      onOpenChange={(next) => !createProject.isPending && onOpenChange(next)}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>
            Claude reviews each new project against your existing portfolio.
          </DialogDescription>
        </DialogHeader>
        {/* Content unmounts when the dialog closes, so the form starts empty each time. */}
        <ProjectForm
          saving={createProject.isPending}
          onSubmit={(values, setError) =>
            createProject.mutate(values, {
              onSuccess: (project) => onCreated(project),
              onError: (error) => applyServerErrors(error, setError),
            })
          }
        />
      </DialogContent>
    </Dialog>
  )
}

interface ProjectFormProps {
  saving: boolean
  onSubmit: (values: ProjectFormOutput, setError: UseFormSetError<ProjectFormInput>) => void
}

function ProjectForm({ saving, onSubmit }: ProjectFormProps) {
  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ProjectFormInput, unknown, ProjectFormOutput>({
    resolver: zodResolver(projectFormSchema, { error: projectFormErrorMap }),
    defaultValues: emptyProjectForm,
  })
  const timeline = useFieldArray({ control, name: 'timeline' })

  // useId keeps these unique even when other elements on the page use similar names.
  const idPrefix = useId()
  const idFor = (name: FieldPath<ProjectFormInput>) => `${idPrefix}-${name}`
  /** Registration plus the id and error link that `FormField` expects. */
  const inputProps = (name: FieldPath<ProjectFormInput>, error: FieldErrorValue) => ({
    id: idFor(name),
    'aria-invalid': !!error,
    'aria-describedby': error ? `${idFor(name)}-error` : undefined,
    ...register(name),
  })

  const timelineError = errors.timeline?.root?.message ?? errors.timeline?.message

  return (
    <form noValidate onSubmit={handleSubmit((values) => onSubmit(values, setError))}>
      <FieldGroup>
        {errors.root?.server && (
          <Alert variant="destructive">
            <CircleAlertIcon />
            <AlertTitle>Couldn't create the project</AlertTitle>
            <AlertDescription>{errors.root.server.message}</AlertDescription>
          </Alert>
        )}

        <FormField inputId={idFor('title')} label="Title" error={errors.title}>
          <Input {...inputProps('title', errors.title)} />
        </FormField>

        <FormField inputId={idFor('description')} label="Description" error={errors.description}>
          <Textarea rows={4} {...inputProps('description', errors.description)} />
        </FormField>

        <FormField inputId={idFor('industry')} label="Industry" error={errors.industry}>
          <Input
            list={`${idPrefix}-industries`}
            autoComplete="off"
            {...inputProps('industry', errors.industry)}
          />
          <datalist id={`${idPrefix}-industries`}>
            {INDUSTRY_SUGGESTIONS.map((industry) => (
              <option key={industry} value={industry} />
            ))}
          </datalist>
        </FormField>

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            inputId={idFor('budget_min')}
            label="Minimum budget (USD)"
            error={errors.budget_min}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              {...inputProps('budget_min', errors.budget_min)}
            />
          </FormField>
          <FormField
            inputId={idFor('budget_max')}
            label="Maximum budget (USD)"
            error={errors.budget_max}
          >
            <Input
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              {...inputProps('budget_max', errors.budget_max)}
            />
          </FormField>
        </div>

        <FieldSet>
          <FieldLegend variant="label">Timeline (optional)</FieldLegend>
          {timeline.fields.map((item, index) => {
            const itemErrors = errors.timeline?.[index]
            return (
              <div key={item.id} className="grid grid-cols-[1fr_auto_auto] items-start gap-2">
                <FormField
                  inputId={idFor(`timeline.${index}.goal`)}
                  label={`Milestone ${index + 1} goal`}
                  hideLabel
                  error={itemErrors?.goal}
                >
                  <Input
                    placeholder="Milestone"
                    {...inputProps(`timeline.${index}.goal`, itemErrors?.goal)}
                  />
                </FormField>
                <FormField
                  inputId={idFor(`timeline.${index}.due_at`)}
                  label={`Milestone ${index + 1} due date`}
                  hideLabel
                  error={itemErrors?.due_at}
                >
                  <Input
                    type="date"
                    {...inputProps(`timeline.${index}.due_at`, itemErrors?.due_at)}
                  />
                </FormField>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove milestone ${index + 1}`}
                  onClick={() => timeline.remove(index)}
                >
                  <Trash2Icon />
                </Button>
              </div>
            )
          })}
          {timelineError && <FieldError>{timelineError}</FieldError>}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => timeline.append(emptyTimelineItem)}
          >
            <PlusIcon data-icon="inline-start" />
            Add milestone
          </Button>
        </FieldSet>
      </FieldGroup>

      <DialogFooter className="mt-6">
        <DialogClose asChild>
          <Button type="button" variant="outline" disabled={saving}>
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={saving}>
          {saving && <Spinner data-icon="inline-start" aria-hidden="true" />}
          {saving ? 'Creating…' : 'Create project'}
        </Button>
      </DialogFooter>
    </form>
  )
}

type FieldErrorValue = { message?: string } | undefined

interface FormFieldProps {
  inputId: string
  label: string
  error: FieldErrorValue
  hideLabel?: boolean
  children: ReactNode
}

/** Label, control and error message; the control must use `inputId` (see `inputProps`). */
function FormField({ inputId, label, error, hideLabel = false, children }: FormFieldProps) {
  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={inputId} className={hideLabel ? 'sr-only' : undefined}>
        {label}
      </FieldLabel>
      {children}
      <FieldError id={`${inputId}-error`} errors={[error]} />
    </Field>
  )
}

const FORM_FIELD_PATH =
  /^(title|description|industry|budget_min|budget_max|timeline(\.\d+\.(goal|due_at))?)$/

const isFormFieldPath = (path: string): path is FieldPath<ProjectFormInput> =>
  FORM_FIELD_PATH.test(path)

/** Show a failed create on the form: 422 issues on their fields, anything else at the top. */
function applyServerErrors(error: unknown, setError: UseFormSetError<ProjectFormInput>): void {
  const issues = validationIssues(error)
  const unplaced: string[] = []
  for (const { path, message } of issues) {
    if (isFormFieldPath(path)) setError(path, { type: 'server', message })
    else unplaced.push(message)
  }
  if (issues.length === 0) unplaced.push(errorMessage(error))
  if (unplaced.length > 0) setError('root.server', { type: 'server', message: unplaced.join(' ') })
}
