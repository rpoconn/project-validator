import { defineConfig } from '@hey-api/openapi-ts'

// Regenerate with `npm run gen:api` (exports the spec from the backend, then runs this config).
export default defineConfig({
  input: './openapi.json',
  output: 'src/api/generated',
  plugins: [
    { name: '@hey-api/client-fetch', runtimeConfigPath: './src/api/clientConfig' },
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
    'zod',
  ],
})
