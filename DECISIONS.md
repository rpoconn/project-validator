# Decisions

A short log of the plan, the main technical and product decisions, how I verified the result, and
what I'd do next. The full phase-by-phase build notes are in [PLAN.md](PLAN.md).

## Plan

1. Project setup: repo layout, uv and npm, lint/format/type-check tooling for both apps.
2. Backend logic and API: the project model, CRUD endpoints, OpenAPI spec and the generated client.
3. AI logic and calls: the review provider, prompt, retries and error handling.
4. Frontend: the master-detail UI, intake form and review panel.
5. Testing, cleanup and polish: e2e tests, mock mode, Docker and docs.

## Key decisions and why

### Technical

#### 1. TypeScript + Python
I'm most familiar with these, so I could move fast and focus on the problem rather than the tooling.

#### 2. shadcn/ui for components
shadcn gives a clean default theme without much setup. MUI felt too heavyweight for an app this
size. TanStack's UI toolkit was a close second, but I haven't used it as much. (TanStack Query is
still used for data fetching.)

#### 3. Anthropic as the LLM provider, with OpenAI as an option
A baseline OpenAI key wasn't provided, and I had Claude tokens on hand, so that was easier. I also
added an OpenAI provider in case whoever tests the project uses that service instead.

#### 4. A provider interface instead of LangChain/LangGraph
The backend defines a small provider interface (`backend/src/features/reviews/provider.py`) with
Anthropic, OpenAI, and mock implementations. I'd consider LangChain/LangGraph in a production app,
but this is a single agent call with no routing or multiple hops, so a graph framework would be
overkill.

#### 5. hey-api for the typed client
I've used `@hey-api` before. It's good at turning an OpenAPI spec into typed TypeScript inputs and
outputs for REST calls. The default OpenAPI generator isn't as good, and it still requires
TypeScript 5, which is an odd requirement now that the community is on 6 or 7. I ran into peer
dependency issues with it.

#### 6. Types everywhere
The backend, the SQL layer, and the frontend are all typed. The instructions asked for this too, but
in my experience typed projects are easier for both humans and LLMs to read, and they hold fewer
surprises.

#### 7. Playwright for end-to-end testing
The app is small and has only a few user paths, so Playwright end-to-end tests cover the key
workflows well without much overhead.

#### 8. Background job + polling for reviews
This was listed as a nice-to-have, but I treated it as necessary. If the LLM is slow or needs to
retry, a long-running synchronous request can have its connection dropped. Starting the review in
the background and polling for the result is much more robust. SSE or WebSockets would be the next
step up, but I limited scope to save time.

#### 9. Separate frontend and backend Docker images
This was the quickest route given the time I had. In production the UI would be served from a CDN,
and the backend would be the only container. The exception would be if we needed SSR, which helps
when latency and SEO matter. This app is small enough that SSR wouldn't buy much.

### Product: in scope

#### 10. Send all projects to the LLM
Every project goes to the LLM along with the one under review, so it can point out other projects
whose timelines might interfere. This is heavyweight. A better approach would be to send a short
date summary of the other projects. That would give Gantt-chart-style insight into periods when the
team is overloaded, at a fraction of the size. This was an extra, but I thought it was a nice
addition and wanted to explain the choice.

#### 11. Master-detail layout
A master-detail list shows all projects at once and makes navigation easy. The idea was that the
user could see everything in one pane of glass without swapping pages out. I also added Edit and
Delete. They weren't required, but they made testing much easier on my end.

### Product: out of scope

#### 12. No users or login
I left out authentication to focus on the task as outlined, rather than add a lot of extra code and
scope.

## How I verified it works

- **Manually.** I ran through the key workflows in the browser against a live backend: create a
  project, watch the review complete, open it in the list and detail views, edit and delete, re-run
  a review, and the error paths (empty and invalid form submits, invalid API key, no key, re-run
  while pending, server restart mid-review, a prompt-injection attempt in a description). I
  repeated the main flow in `LLM_MOCK=1` mode and through the Docker stack.
- **Unit and integration tests.** pytest on the backend (schemas, services, prompt builder, routers
  through an in-process client, both providers against scripted SDK clients) and Vitest on the
  frontend (form schema, dialog, list/detail states, polling, every review state).
- **End-to-end tests.** Playwright runs the real backend and frontend in mock mode and covers the
  empty state, validation, creation, a completed review, and a failed review recovered with "Retry
  review".

The README's [Verification](README.md#c-verification) section has the commands and the detail.

## Tradeoffs: what I did not do, and why

- **No users or login** (decision 12). Not asked for, and it would have added a lot of scope.
- **Polling instead of SSE or WebSockets** (decision 8). Polling every 2 s was enough for a small
  app and much quicker to build and test.
- **No job queue.** Reviews run as in-process background tasks, so they die with the server. I
  handled that by marking interrupted reviews as "unreviewed" with a re-run button rather than
  adding a worker.
- **Whole projects in the prompt, not a date summary** (decision 10). Simpler to build, but it
  sends more tokens than it needs to and won't scale past a few dozen projects.
- **Two Docker images rather than a CDN-served UI** (decision 9). Quickest to get running.
- **No LangChain/LangGraph** (decision 4). A single LLM call doesn't need a graph framework.
- **Basic LLM verification.** The LLM output is schema-validated and the providers are tested
  against scripted responses, but I didn't evaluate the quality of the reviews beyond reading them.

## What I learned, or would do differently

- I'd send the LLM a compact date summary of the other projects instead of every project in full
  (decision 10). It would be cheaper, scale better, and probably give better scheduling insight.
- The manual browser pass caught a bug the unit tests missed (a duplicated element id between the
  detail heading and the form's Title input). I'd write the e2e tests earlier next time rather than
  at the end.
- Switching to shadcn/ui partway through cost some time. I'd pick the component library before
  starting the frontend.

## If I had one more day

- Polish the UI.
- Login and accounts.
- Better LLM testing and verification. What's there is very basic: more unit tests around the
  LLM call and some evaluation of the review quality itself.
- Push notifications (SSE) instead of polling, and the date-summary prompt from decision 10.

## Time

Under three hours of work, with a 30-minute break in the middle, so the recording timestamps may
show slightly over three hours.
