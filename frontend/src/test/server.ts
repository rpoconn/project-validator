import { setupServer } from 'msw/node'

/** Shared MSW server; tests register handlers with `server.use(...)`. */
export const server = setupServer()
