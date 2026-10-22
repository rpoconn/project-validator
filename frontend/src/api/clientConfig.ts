import type { CreateClientConfig } from './generated/client.gen'

/** Runtime config for the generated API client (wired in via `runtimeConfigPath`). */
export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: import.meta.env.VITE_API_BASE_URL || window.location.origin,
})
