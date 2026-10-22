# Decisions

A short log of the main technical and product decisions behind this project, and why I made them.

## Technical

### 1. TypeScript + Python
I'm most familiar with these, so I could move fast and focus on the problem rather than the tooling.

### 2. shadcn/ui for components
shadcn gives a clean default theme without much setup. MUI felt too heavyweight for an app this size. TanStack was a close second, but I haven't used it as much.

### 3. Anthropic as the LLM provider, with OpenAI as an option
I used Anthropic because that's where I had tokens. I also added an OpenAI provider in case whoever tests the project uses that service instead. I didn't get an API token from Andy, so I just went with what I had.

### 4. A provider interface instead of LangChain/LangGraph
The backend defines a small provider interface (`backend/src/features/reviews/provider.py`) with Anthropic, OpenAI, and mock implementations. I'd consider LangChain/LangGraph in a production app, but this is a single agent call with no routing or multiple hops, so a graph framework would be overkill.

### 5. hey-api for the typed client
I've used `@hey-api` before. It's good at turning an OpenAPI spec into typed TypeScript inputs and outputs for REST calls. The default OpenAPI generator isn't as good, and it requires TypeScript 5, which is an odd requirement now that the community is on 7. I ran into peer dependency issues with it.

### 6. Types everywhere
The backend, the SQL layer, and the frontend are all typed. The instructions asked for this too, but in my experience typed projects are easier for both humans and LLMs to read, and they hold fewer surprises.

### 7. Playwright for end-to-end testing
The app is small and has only a few user paths, so Playwright end-to-end tests cover the key workflows well without much overhead.     

### 8. Background job + polling for reviews
This was listed as a nice-to-have, but I treated it as necessary. If the LLM is slow or needs to retry, a long-running synchronous request can have its connection dropped. Starting the review in the background and polling for the result is much more robust. SSE or WebSockets would be the next step up, but I limited scope to save time.

### 9. Separate frontend and backend Docker images
This was the quickest route given the time I had. In production the UI would be served from a CDN, and the backend would be the only container. The exception would be if we needed SSR, which helps when latency and SEO matter. This app is small enough that SSR wouldn't buy much.

## Product: In Scope

### 10. Send all projects to the LLM
Every project goes to the LLM along with the one under review, so it can point out other projects whose timelines might interfere. This is heavyweight. A better approach would be to send a short date summary of the other projects. That would give Gantt-chart-style insight into periods when the team is overloaded, at a fraction of the size. This was an extra, but I thought it was a nice addition and wanted to explain the choice.

### 11. Master-detail layout
A master-detail list shows all projects at once and makes navigation easy. I also added Edit and Delete. They weren't required, but they made testing much easier on my end.  The idea was that user could see everything with one pane of glass without swaping pages out.

## Product: Out of Scope

### 12. No users or login
I left out authentication to focus on the task as outlined, rather than add a lot of extra code and scope.
