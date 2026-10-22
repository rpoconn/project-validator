import { useQuery } from '@tanstack/react-query'
import { InfoIcon, TriangleAlertIcon } from 'lucide-react'

import { getHealthOptions } from '@/api/generated/@tanstack/react-query.gen'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

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
          The backend is running with LLM_MOCK enabled, so reviews are canned and Claude is never
          called.
        </AlertDescription>
      </Alert>
    )
  }

  if (data.anthropic_configured) return null

  return (
    <Alert>
      <TriangleAlertIcon />
      <AlertTitle>AI reviews are unavailable</AlertTitle>
      <AlertDescription>
        The backend has no ANTHROPIC_API_KEY configured, so reviews will fail. Set it in .env and
        restart the server, then retry the review.
      </AlertDescription>
    </Alert>
  )
}
