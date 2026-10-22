import { MousePointerClickIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'

import type { ProjectRead } from '@/api/generated/types.gen'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { HealthBanner } from '@/features/health/HealthBanner'
import { ProjectDetail } from '@/features/projects/ProjectDetail'
import { ProjectFormDialog } from '@/features/projects/ProjectFormDialog'
import { ProjectList } from '@/features/projects/ProjectList'

export default function App() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // The project stays set while the dialog closes so its title doesn't change mid-animation.
  const [form, setForm] = useState<{ open: boolean; project?: ProjectRead }>({ open: false })
  const openCreate = () => setForm({ open: true })
  const closeForm = () => setForm((current) => ({ ...current, open: false }))

  return (
    <div className="mx-auto flex min-h-svh max-w-6xl flex-col gap-4 p-4 md:p-6">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Project Tracker</h1>
        <Button onClick={openCreate}>
          <PlusIcon data-icon="inline-start" />
          New project
        </Button>
      </header>

      <HealthBanner />

      <div className="grid flex-1 items-start gap-4 md:grid-cols-[320px_1fr]">
        <nav aria-label="Project list">
          <ProjectList selectedId={selectedId} onSelect={setSelectedId} onCreate={openCreate} />
        </nav>
        <main>
          {selectedId === null ? (
            <Empty className="border border-dashed">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <MousePointerClickIcon />
                </EmptyMedia>
                <EmptyTitle>Select a project</EmptyTitle>
                <EmptyDescription>
                  Its details and AI risk review will appear here.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ProjectDetail
              key={selectedId}
              projectId={selectedId}
              onEdit={(project) => setForm({ open: true, project })}
              onDeleted={() => setSelectedId(null)}
            />
          )}
        </main>
      </div>

      <ProjectFormDialog
        open={form.open}
        onOpenChange={(open) => (open ? setForm((current) => ({ ...current, open })) : closeForm())}
        project={form.project}
        onSaved={(project) => {
          setSelectedId(project.id)
          closeForm()
        }}
      />
    </div>
  )
}
