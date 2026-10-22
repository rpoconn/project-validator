import { CircleAlertIcon } from 'lucide-react'

import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface ErrorBannerProps {
  title: string
  message: string
  onRetry?: () => void
  retrying?: boolean
}

export function ErrorBanner({ title, message, onRetry, retrying = false }: ErrorBannerProps) {
  return (
    <Alert variant="destructive">
      <CircleAlertIcon />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
      {onRetry && (
        <AlertAction>
          <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
            Retry
          </Button>
        </AlertAction>
      )}
    </Alert>
  )
}
