import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import type { HealthResponse } from '@/api/generated/types.gen'
import { renderWithQueryClient } from '@/test/render'
import { server } from '@/test/server'

import { HealthBanner } from './HealthBanner'

function serveHealth(overrides: Partial<HealthResponse> = {}) {
  const body: HealthResponse = {
    status: 'ok',
    llm_provider: 'anthropic',
    llm_configured: true,
    llm_mock: false,
    ...overrides,
  }
  server.use(http.get('*/api/health', () => HttpResponse.json(body)))
}

describe('HealthBanner', () => {
  it('renders nothing while loading and nothing when reviews are configured', async () => {
    serveHealth()

    const { queryClient } = renderWithQueryClient(<HealthBanner />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says reviews are mocked, even when no key is configured', async () => {
    serveHealth({ llm_mock: true, llm_configured: false })

    renderWithQueryClient(<HealthBanner />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('AI reviews are mocked')
    expect(alert).toHaveTextContent('LLM_MOCK')
    expect(alert).not.toHaveTextContent('unavailable')
  })

  it.each([
    ['anthropic', 'Anthropic', 'ANTHROPIC_API_KEY'],
    ['openai', 'OpenAI', 'OPENAI_API_KEY'],
  ] as const)('names the %s key when it is missing', async (provider, name, keyVar) => {
    serveHealth({ llm_provider: provider, llm_configured: false })

    renderWithQueryClient(<HealthBanner />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('AI reviews are unavailable')
    expect(alert).toHaveTextContent(`Reviews use ${name}, but the backend has no ${keyVar}`)
  })

  it('stays hidden when the health check fails', async () => {
    server.use(http.get('*/api/health', () => HttpResponse.error()))

    const { queryClient } = renderWithQueryClient(<HealthBanner />)

    await waitFor(() => expect(queryClient.isFetching()).toBe(0))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
