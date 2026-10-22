import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlertIcon, PlusIcon, Trash2Icon } from 'lucide-react'
import { type ReactNode, useEffect, useId, useState } from 'react'
import {
  type FieldPath,
  type RegisterOptions,
  useFieldArray,
  useForm,
  type UseFormSetError,
} from 'react-hook-form'

import { errorMessage, isApiError, validationIssues } from '@/api/errors'
import type { ProjectRead } from '@/api/generated/types.gen'
import { useCreateProject, useUpdateProject } from '@/api/projects'
import { ConfirmDialog } from '@/components/ConfirmDialog'
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
  toProjectFormInput,
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

type FormMode = 'create' | 'edit'

const COPY: Record<
  FormMode,
  {
    title: string
    description: string
    submit: string
    submitting: string
    failed: string
    discardTitle: string
    discardDescription: string
    proceedWithoutTimeline: string
  }
> = {
  create: {
    title: 'New project',
    description: 'Each new project gets an AI review against your existing portfolio.',
    submit: 'Create project',
    submitting: 'Creating…',
    failed: "Couldn't create the project",
    discardTitle: 'Discard this project?',
    discardDescription: "The details you've entered haven't been saved.",
    proceedWithoutTimeline: 'Create anyway',
  },
  edit: {
    title: 'Edit project',
    description: 'Saving starts a fresh AI review of the updated details.',
    submit: 'Save changes',
    submitting: 'Saving…',
    failed: "Couldn't save the project",
    discardTitle: 'Discard your changes?',
    discardDescription: "Your changes haven't been saved.",
    proceedWithoutTimeline: 'Save anyway',
  },
}

interface ProjectFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When set, the dialog edits this project instead of creating a new one. */
  project?: ProjectRead
  onSaved: (project: ProjectRead) => void
}

export function ProjectFormDialog({
  open,
  onOpenChange,
  project,
  onSaved,
}: ProjectFormDialogProps) {
  const createProject = useCreateProject()
  const updateProject = useUpdateProject()
  const saving = createProject.isPending || updateProject.isPending
  const [dirty, setDirty] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  // A valid submission waiting for the user to confirm saving without any milestones.
  const [withoutTimeline, setWithoutTimeline] = useState<Submission | null>(null)

  const mode: FormMode = project ? 'edit' : 'create'
  const copy = COPY[mode]

  // Every way of closing (overlay click, Escape, the X and Cancel buttons) comes through here.
  const requestClose = (next: boolean) => {
    // Stay open while saving so the result (or a validation error) isn't lost.
    if (saving) return
    if (!next && dirty) {
      setConfirmDiscard(true)
      return
    }
    onOpenChange(next)
  }

  const save = ({ values, form }: Submission) => {
    const callbacks = {
      onSuccess: (saved: ProjectRead) => onSaved(saved),
      onError: (error: unknown) => applyServerErrors(error, form.setError),
    }
    if (project) updateProject.mutate({ projectId: project.id, body: values }, callbacks)
    else createProject.mutate(values, callbacks)
  }

  const submit = (submission: Submission) => {
    // An empty timeline is valid but usually an oversight, so check before saving.
    if (submission.values.timeline.length === 0) setWithoutTimeline(submission)
    else save(submission)
  }

  return (
    <Dialog open={open} onOpenChange={requestClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
          <p className="text-xs text-muted-foreground">
            <RequiredMark /> Required field
          </p>
        </DialogHeader>
        {/* Content unmounts when the dialog closes, so the form starts fresh each time. */}
        <ProjectForm
          mode={mode}
          defaultValues={project ? toProjectFormInput(project) : emptyProjectForm}
          saving={saving}
          onDirtyChange={setDirty}
          onSubmit={submit}
        />

        {/*
          The prompts render inside the dialog's React tree so Radix treats clicks on them as
          inside the dialog; as siblings, a click on a prompt could also dismiss the dialog.
        */}
        <ConfirmDialog
          open={confirmDiscard}
          onOpenChange={setConfirmDiscard}
          title={copy.discardTitle}
          description={copy.discardDescription}
          cancelLabel="Keep editing"
          confirmLabel="Discard"
          destructive
          onConfirm={() => {
            setConfirmDiscard(false)
            onOpenChange(false)
          }}
        />

        <ConfirmDialog
          open={withoutTimeline !== null}
          onOpenChange={(next) => !next && setWithoutTimeline(null)}
          title="No milestones yet"
          description="Most projects have at least one milestone, so this may be an oversight. Save it without a timeline?"
          cancelLabel="Add a milestone"
          confirmLabel={copy.proceedWithoutTimeline}
          onCancel={() => withoutTimeline?.form.addMilestone()}
          onConfirm={() => {
            if (withoutTimeline) save(withoutTimeline)
            setWithoutTimeline(null)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}

/** What the form hands back on submit: the API payload plus hooks back into the form. */
interface Submission {
  values: ProjectFormOutput
  form: {
    setError: UseFormSetError<ProjectFormInput>
    addMilestone: () => void
  }
}

interface ProjectFormProps {
  mode: FormMode
  defaultValues: ProjectFormInput
  saving: boolean
  onDirtyChange: (dirty: boolean) => void
  onSubmit: (submission: Submission) => void
}

function ProjectForm({ mode, defaultValues, saving, onDirtyChange, onSubmit }: ProjectFormProps) {
  const copy = COPY[mode]
  const {
    register,
    control,
    handleSubmit,
    setError,
    getValues,
    getFieldState,
    trigger,
    formState: { errors, isDirty },
  } = useForm<ProjectFormInput, unknown, ProjectFormOutput>({
    resolver: zodResolver(projectFormSchema, { error: projectFormErrorMap }),
    defaultValues,
  })
  const timeline = useFieldArray({ control, name: 'timeline' })

  // Let the dialog know whether closing would lose anything; a closed form has nothing to lose.
  useEffect(() => {
    onDirtyChange(isDirty)
    return () => onDirtyChange(false)
  }, [isDirty, onDirtyChange])

  // useId keeps these unique even when other elements on the page use similar names.
  const idPrefix = useId()
  const idFor = (name: FieldPath<ProjectFormInput>) => `${idPrefix}-${name}`
  /** Registration plus the id and error link that `FormField` expects. */
  const inputProps = (
    name: FieldPath<ProjectFormInput>,
    error: FieldErrorValue,
    options?: RegisterOptions<ProjectFormInput>,
  ) => ({
    id: idFor(name),
    'aria-required': true,
    'aria-invalid': !!error,
    'aria-describedby': error ? `${idFor(name)}-error` : undefined,
    ...register(name, options),
  })

  // The range error lives on the maximum, so re-check it as either budget changes rather than
  // waiting for submit (or, after submit, for the maximum itself to change). A maximum that is
  // still blank and error-free is left alone so the user isn't told "Required" mid-entry.
  const budgetOptions: RegisterOptions<ProjectFormInput> = {
    onChange: () => {
      if (getValues('budget_max').trim() || getFieldState('budget_max').error) {
        void trigger('budget_max')
      }
    },
  }

  const timelineError = errors.timeline?.root?.message ?? errors.timeline?.message

  return (
    <form
      noValidate
      onSubmit={handleSubmit((values) =>
        onSubmit({
          values,
          form: { setError, addMilestone: () => timeline.append(emptyTimelineItem) },
        }),
      )}
    >
      <FieldGroup>
        {errors.root?.server && (
          <Alert variant="destructive">
            <CircleAlertIcon />
            <AlertTitle>{copy.failed}</AlertTitle>
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
              {...inputProps('budget_min', errors.budget_min, budgetOptions)}
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
              {...inputProps('budget_max', errors.budget_max, budgetOptions)}
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
          {saving ? copy.submitting : copy.submit}
        </Button>
      </DialogFooter>
    </form>
  )
}

/** The asterisk that marks a required field; the note under the dialog title explains it. */
function RequiredMark() {
  return (
    <span aria-hidden="true" className="text-destructive">
      *
    </span>
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

/**
 * Label, control and error message for one of the form's (all required) fields; the control must
 * use `inputId` (see `inputProps`).
 */
function FormField({ inputId, label, error, hideLabel = false, children }: FormFieldProps) {
  return (
    <Field data-invalid={!!error}>
      {hideLabel ? (
        <FieldLabel htmlFor={inputId} className="sr-only">
          {label}
        </FieldLabel>
      ) : (
        // The mark sits outside the label so the field's accessible name stays just the label.
        <div className="flex w-fit items-baseline gap-1">
          <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
          <RequiredMark />
        </div>
      )}
      {children}
      <FieldError id={`${inputId}-error`} errors={[error]} />
    </Field>
  )
}

const FORM_FIELD_PATH =
  /^(title|description|industry|budget_min|budget_max|timeline(\.\d+\.(goal|due_at))?)$/

const isFormFieldPath = (path: string): path is FieldPath<ProjectFormInput> =>
  FORM_FIELD_PATH.test(path)

const REVIEW_IN_PROGRESS_MESSAGE =
  'A review of this project is still running. Wait for it to finish, then try again.'

/** Show a failed save on the form: 422 issues on their fields, anything else at the top. */
function applyServerErrors(error: unknown, setError: UseFormSetError<ProjectFormInput>): void {
  const issues = validationIssues(error)
  const unplaced: string[] = []
  for (const { path, message } of issues) {
    if (isFormFieldPath(path)) setError(path, { type: 'server', message })
    else unplaced.push(message)
  }
  if (issues.length === 0) {
    unplaced.push(isApiError(error, 409) ? REVIEW_IN_PROGRESS_MESSAGE : errorMessage(error))
  }
  if (unplaced.length > 0) setError('root.server', { type: 'server', message: unplaced.join(' ') })
}
