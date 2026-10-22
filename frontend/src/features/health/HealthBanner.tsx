import { useQuery } from '@tanstack/react-query'
import { InfoIcon, TriangleAlertIcon } from 'lucide-react'

import { getHealthOptions } from '@/api/generated/@tanstack/react-query.gen'
import type { LlmProvider } from '@/api/generated/types.gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

const PROVIDERS: Record<LlmProvider, { name: string; keyVar: string }> = {
  anthropic: { name: 'Anthropic', keyVar: 'ANTHROPIC_API_KEY' },
  openai: { name: 'OpenAI', keyVar: 'OPENAI_API_KEY' },
}

/** Says when AI reviews are mocked or can't run. Unreachable-backend errors surface elsewhere. */
export function HealthBanner() {
  const { data } = useQuery(getHealthOptions())

  if (!data) return null

  if (data.llm_mock) {
    return (
      <Alert>
        <InfoIcon />
        <AlertTitle>AI reviews are mocked</AlertTitle>
        <AlertDescription>
          The backend is running with LLM_MOCK enabled, so reviews are canned and no AI provider is
          called.
        </AlertDescription>
      </Alert>
    )
  }

  if (data.llm_configured) return null

  const provider = PROVIDERS[data.llm_provider]

  return (
    <Alert>
      <TriangleAlertIcon />
      <AlertTitle>AI reviews are unavailable</AlertTitle>
      <AlertDescription>
        Reviews use {provider.name}, but the backend has no {provider.keyVar} configured, so they
        will fail. Set ANTHROPIC_API_KEY or OPENAI_API_KEY (and optionally LLM_PROVIDER) in .env and
        restart the server, then retry the review.
      </AlertDescription>
    </Alert>
  )
}
