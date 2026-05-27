# Fulcrum Chat

Full-stack AI chatbot: **Vercel AI SDK v6** frontend + **PydanticAI** backend.

## Stack

- **Backend**: Python 3.13, FastAPI, PydanticAI, PostgreSQL (asyncpg), SQLAlchemy
- **Frontend**: TypeScript, React 19, Vercel AI SDK v6 (`@ai-sdk/react`), TanStack Query, shadcn/ui, AI Elements, TailwindCSS v4

## Running the Project

### Backend (Python/FastAPI)

```bash
# From project root
uv run uvicorn main:app --reload --port 8000
```

Runs at http://localhost:8000

### Frontend (React/Vite)

```bash
cd frontend
npm install  # First time only
npm run dev
```

Runs at http://localhost:5173

### Database (PostgreSQL)

Start PostgreSQL for local development:
```bash
docker compose up db -d
```

Run migrations:
```bash
uv run alembic upgrade head                          # Postgres schema (platform data)
uv run python scripts/apply_delta_migrations.py      # Delta schema (raw + derived)
```

Two migration systems run in parallel: Alembic owns the Postgres schema (conversations, task outputs, auth); `apply_delta_migrations.py` owns the Delta Lake schemas under `data/migrations/{raw,derived}/<table>/NNN_*.py`. Raw migrations are written by the `ingest-data` skill before the first ingest; derived migrations by the `extend-ontology` skill before any task implementation. See `docs/ontology-pipeline.md` for the full pipeline.

Or run the full stack locally via Docker:
```bash
docker compose up -d --build
```
Both migration systems run automatically on container startup via `entrypoint.sh`.

Seed data (template dev only — not for customer forks):
```bash
uv run python scripts/seed.py    # standalone
./start.sh --seed                # or via start.sh flag
```

## Structure

```
backend/
  api/
    dependencies.py              # FastAPI Depends() providers (central DI)
    routers/chat.py              # Chat endpoints, agent invocation
  core/
    agents/chat_agent.py         # PydanticAI agent with toolbox-aware tool selection
    agents/deps.py               # AgentDeps dataclass
    interfaces/                  # Abstract interfaces (protocols/ABCs)
      filesystem.py              # FileSystem protocol
      prompt_loader.py           # PromptLoader protocol (takes toolbox)
      conversation_repository.py # ConversationRepositoryInterface
    tools/execute_sql/           # execute_sql tool (generic, shared)
    tools/read_file/             # read_file + list_files tools (generic, shared)
    tasks/generate_signals.py    # Example task: generates signals as task outputs
    services/compaction.py       # Conversation compaction service
  customer/                      # ★ Customer carveout — only customer-specific code
    toolboxes.py                 # Toolbox StrEnum (Sales, Production)
    queries.py                   # DashboardQuery StrEnum + DASHBOARD_QUERIES registry
    tools/__init__.py            # TOOLBOX_TOOLS: maps toolbox → tool list
    tasks/__init__.py            # TOOLBOX_TASKS: maps toolbox → task list
  infrastructure/
    db/                          # SQLAlchemy engine, models, repositories
    filesystem/                  # LocalFileSystem implementation
    prompts/local.py             # FilePromptLoader: loads system.md + {toolbox}.md
  prompts/                       # Prompt markdown files (data, not code)
    system.md                    # Shared persona + company context
    sales.md                     # Sales toolbox instructions
    production.md                # Production toolbox instructions
  config.py                      # Settings (env vars, paths)
data/documents/                  # Root directory for file tools
data/datasets/                   # Delta Lake tables + DuckDB views (data)
data/migrations/                 # Delta schema migrations (raw/<table>/, derived/<table>/)
frontend/src/
  customer/                      # ★ Customer carveout — toolbox registry + views
    toolboxes.ts                 # Toolbox enum + registry (drives sidebar + routing)
    queries.ts                   # DashboardQuery const (must match backend registry)
    sales/SalesChat.tsx          # Sales chat wrapper
    sales/SalesSignals.tsx       # Sales signals wrapper
    production/ProductionChat.tsx
    production/ProductionSignals.tsx
  components/
    AppSidebar.tsx               # Accordion sidebar from toolbox registry
    Chat.tsx                     # useChat() with X-Toolbox header
    ai-elements/                 # AI Elements components
    ui/                          # shadcn/ui components
  lib/queries.ts                 # TanStack Query keys, fetch functions, types
scripts/
  check_customer_config.py       # Validates FE/BE toolbox + query registry consistency
tests/evals/
  _runner.py, _report.py, ...    # Agent eval framework (template, owned upstream)
  customer/                      # ★ Customer carveout — agent eval cases per toolbox
```

## UI Components

Use **shadcn/ui** and **AI Elements** for UI - never create components manually.

### Installing shadcn/ui components

```bash
cd frontend
npx shadcn@latest add <component-name>
# Examples:
npx shadcn@latest add button card dialog
```

### Installing AI Elements components

```bash
cd frontend
npx shadcn@latest add "https://ai-sdk.dev/elements/api/registry/<component-name>.json" --overwrite
# Examples:
npx shadcn@latest add "https://ai-sdk.dev/elements/api/registry/conversation.json" --overwrite
npx shadcn@latest add "https://ai-sdk.dev/elements/api/registry/message.json" --overwrite
npx shadcn@latest add "https://ai-sdk.dev/elements/api/registry/tool.json" --overwrite
```

AI Elements are AI-specific components (conversation, message, prompt-input, tool, reasoning) that integrate with Vercel AI SDK hooks.

**Note**: After installing, check import paths in the component file - change `@/registry/default/ui/` to `@/components/ui/`.

## Git

- **Never** add `Co-Authored-By` lines to commit messages.
- Start commit messages with an imperative verb (e.g. "Add", "Fix", "Remove").
- Keep the subject line short. Use the body for context/reasoning if needed.
- PR descriptions: summary only. **No test plan sections.**

## Code Style

- **Python**: Always use type hints. `def fn(x: str) -> Result | None:`
- **TypeScript**: Strict mode. Explicit types, no `any`.

## Dependencies

Pin **exact versions** for all dependencies in both the Python backend (`pyproject.toml`) and the TypeScript frontend (`package.json`). No version ranges (`^`, `~`, `>=`, `*`) — use exact pins (e.g. `"react": "19.0.0"`, `fastapi==0.115.0`). Lockfiles (`uv.lock`, `package-lock.json`) must be committed.

When updating or installing a new dependency, **do not jump to the newest release.** Prefer versions that have been published long enough to surface supply chain issues (malicious releases, compromised maintainer accounts, regressions) — aim for releases at least a few weeks old, and check the changelog and registry page before upgrading. This reduces exposure to supply chain attacks and freshly published malicious packages.

**Exception — CVE fixes:** when a scanner (`pip-audit`, `npm audit`) reports a vulnerability, update to the exact version the scanner recommends, or the first published version that addresses the CVE. Do not wait out the usual aging period for security fixes.

## Data Fetching

Use **TanStack Query** (`@tanstack/react-query`) for all server state fetching — never use raw `fetch` in `useEffect`.

- Query keys and fetch functions live in `frontend/src/lib/queries.ts`
- Use `useQuery` for GET requests, `useMutation` for POST/PUT/DELETE
- Invalidate related queries on mutations via `queryClient.invalidateQueries()`
- Do not manage server state with `useState` + `useEffect`

## Key Integration

Backend `/api/chat` uses `VercelAIAdapter` with `run_stream(message_history=...)`.

Frontend uses `useChat({ transport: new DefaultChatTransport({ api: '/api/chat' }) })`.

Tool calls appear as `tool-{name}` message parts.

### Message history flow

The frontend sends **only the latest message** via `prepareSendMessagesRequest` — not the full conversation. The backend is the source of truth for history:

1. **Request**: Frontend sends one message. Backend loads prior history from DB (`load_messages_for_agent`).
2. **LLM invocation**: `VercelAIAdapter.run_stream_native()` combines them: `[*db_history, *request_message]`.
3. **Persistence** (`on_complete`): `extract_new_user_message()` + `result.new_messages()` are saved. The user prompt must be extracted separately because the adapter passes it via `message_history` (not the `prompt` param), so `new_messages()` excludes it.

Do **not** pass full history from the frontend — it will be duplicated with DB history by the adapter.

## Architecture

### Backend layers

- **`core/`** — Business logic, agent config, tool definitions, interfaces (no framework imports)
- **`infrastructure/`** — Concrete implementations (database, filesystem, external APIs)
- **`api/`** — FastAPI routes, dependency injection, wires infrastructure into core

### Interfaces

Interfaces (protocols/ABCs) live in `core/interfaces/`. Implementations live in `infrastructure/`. `core/` code only imports interfaces, never infrastructure — this lets you swap implementations (e.g. `LocalFileSystem` → `AzureBlobFileSystem`) without touching business logic.

- `core/interfaces/filesystem.py` — `FileSystem` protocol
- `core/interfaces/conversation_repository.py` — `ConversationRepositoryInterface` ABC

### Dependency injection

All dependencies are provided via FastAPI `Depends()` through `api/dependencies.py`. This is the single place where infrastructure is wired to interfaces.

- **Request-scoped**: DB sessions, repositories, and `AgentDeps` are created per-request via `Depends()`
- **Background tasks**: Use `get_repository_factory` to get a `RepositoryFactory` callable, then create repos in callbacks/background tasks that outlive the request
- **Never** import `AsyncSessionLocal`, `ConversationRepository`, or construct infrastructure directly in routers or services — always go through `dependencies.py`

```python
# api/dependencies.py provides:
get_db_session()              # AsyncSession (request-scoped)
get_conversation_repository() # ConversationRepositoryInterface
get_agent_deps()              # AgentDeps (with FileSystem)
get_repository_factory()      # RepositoryFactory (for background tasks)
```

### Tools

Tools live in `core/tools/<tool_name>/tool.py` as plain functions. They receive dependencies via PydanticAI's `RunContext[AgentDeps]` — never import infrastructure directly.

```python
# core/tools/read_file/tool.py
def read_file(ctx: RunContext[AgentDeps], file_path: str) -> str:
    return ctx.deps.fs.read_text(file_path)
```

`AgentDeps` (`core/agents/deps.py`) is the shared dependency container referencing interfaces from `core/interfaces/`.

To add a new tool:
1. Create `core/tools/<name>/tool.py` with functions taking `RunContext[AgentDeps]`
2. Add any new interfaces to `core/interfaces/` if the tool needs new infrastructure
3. Add infrastructure implementations under `infrastructure/`
4. Add the tool to the relevant toolbox(es) in `customer/tools/__init__.py` `TOOLBOX_TOOLS`
5. If new deps are needed, extend `AgentDeps` and add a provider in `api/dependencies.py`

### Background Tasks

Tasks live in `core/tasks/<name>.py` as async functions and are triggered via `POST /internal/tasks/{task_name}` (X-API-Key auth).

Two backends behind the `TaskQueue` protocol (`core/interfaces/task_queue.py`), chosen by `TASK_BACKEND`:
- **`procrastinate`** (default) — Postgres-backed jobs with retries, job locks, and durability. Uses `LISTEN/NOTIFY` on the existing DB. Worker runs **in-process** in the FastAPI lifespan (`main.py`).
- **`local`** — `asyncio.create_task()` only. No persistence, no locks. Intended for tests and quick local iteration.

Task registration: Procrastinate tasks are decorated module-level in `backend/infrastructure/tasks/tasks.py` and delegate to the core implementation. The local backend uses closures in `backend/customer/tasks/__init__.py` `build_task_registry()`.

Concurrency / safety: pass `lock=` and `queueing_lock=` to `TaskQueue.enqueue()` for jobs that must not run concurrently (e.g. ingestion keyed on `table`). A duplicate enqueue with a `queueing_lock` already waiting surfaces as `HTTP 409`. Poll status with `GET /internal/tasks/{task_id}`.

Adding a task:
1. Implement the async function in `backend/core/tasks/<name>.py`.
2. Register it in `backend/infrastructure/tasks/tasks.py` with `@app.task(name="...")` plus a shim in `backend/customer/tasks/__init__.py` `build_task_registry()`.
3. Add a validation schema to `backend/api/routers/internal.py` `_TASK_SCHEMAS`.
4. If the task needs new deps, extend `TaskDeps` and the resolver.

### Toolbox Architecture

A **toolbox** is a purpose-built workspace for a specific problem domain. Each toolbox has its own tools, prompts, views, and conversation history.

**Template vs. Customer code:**
- `core/`, `infrastructure/`, `api/` = template code (shared, never customer-specific)
- `backend/customer/`, `frontend/src/customer/` = customer carveout (edit per customer)
- Template never hardcodes toolbox names. Customer code defines which toolboxes exist.

**The `Toolbox` enum** (`backend/customer/toolboxes.py` + `frontend/src/customer/toolboxes.ts`) is the shared contract between frontend and backend. Both sides must match — run `uv run python scripts/check_customer_config.py` to verify.

**How toolbox flows from frontend to backend:**
1. Frontend wrapper component (e.g., `SalesChat.tsx`) passes `toolbox="sales"` to `Chat.tsx`
2. `Chat.tsx` sends it as `X-Toolbox` header with every request
3. Backend `chat.py` router extracts the header, validates against the `Toolbox` enum
4. `PromptLoader.load(toolbox)` composes `system.md + {toolbox}.md`
5. `create_agent(toolbox, ...)` selects tools via `TOOLBOX_TOOLS[toolbox]`

**Conversations are per-toolbox.** The `conversations` table has a `toolbox` column. Each toolbox chat maintains separate conversation history.

**Prompts are NOT Python code.** They're markdown loaded at runtime via `PromptLoader`:
- `backend/prompts/system.md` — shared persona + company context
- `backend/prompts/{toolbox}.md` — toolbox-specific instructions

**Frontend sidebar** is generated from `customer/toolboxes.ts` registry. Routes are `/:toolbox/:view`.

### Adding a new toolbox

1. Add value to `backend/customer/toolboxes.py` `Toolbox` enum
2. Add value to `frontend/src/customer/toolboxes.ts` `Toolbox` enum
3. Add tool mapping in `backend/customer/tools/__init__.py`
4. Add task mapping in `backend/customer/tasks/__init__.py`
5. Create prompt file: `backend/prompts/{toolbox}.md`
6. Create frontend wrapper components in `frontend/src/customer/{toolbox}/`
7. Add toolbox entry to `toolboxes` array in `frontend/src/customer/toolboxes.ts`
8. Run `uv run python scripts/check_customer_config.py` to verify consistency

### Named queries (dashboard data)

Named queries let customer forks expose pre-registered SQL queries via `GET /api/data/query/{query_name}`, returning structured JSON (`columns`, `rows`, `truncated`) for dashboard views.

**Registry files** (customer carveout, must stay in sync):
- `backend/customer/queries.py` — `DashboardQuery` StrEnum + `DASHBOARD_QUERIES` dict mapping names to SQL
- `frontend/src/customer/queries.ts` — `DashboardQuery` const object (same values)

**To add a named query:**
1. Add a member to `DashboardQuery` in `backend/customer/queries.py`
2. Add the SQL string to `DASHBOARD_QUERIES` for that member
3. Add the matching member to `DashboardQuery` in `frontend/src/customer/queries.ts`
4. Run `uv run python scripts/check_customer_config.py` to verify parity

**Frontend usage:** `fetchDashboardQuery(queryName)` and `queryKeys.dashboardQuery(queryName)` in `lib/queries.ts`.

### Forking for a new customer

1. Fork the template repo
2. Edit `backend/customer/` — change toolbox enum, tool mappings, task mappings, query registry
3. Edit `tests/evals/customer/` — replace example eval cases with cases grounded in real customer data
4. Edit `frontend/src/customer/` — change toolbox registry, query registry, and view components
5. Replace `backend/prompts/` with customer-specific prompt files
6. Run `ingest-data` skill to declare customer-specific raw schemas under `data/migrations/raw/<TABLE>/001_initial.py`, ingest the customer's data, and write SQL views in `data/datasets/views/`
7. Create a Supabase project (EU region for EU customers); enable asymmetric JWT signing; set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `INITIAL_ADMIN_EMAILS`, `SITE_URL` (backend) and `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (frontend). See "Authentication (Supabase Auth)" below.
8. Delete `scripts/seed.py` *and* the template-only migrations it created at `data/migrations/raw/{CRM_ACCT,CRM_PURCH_HIST,CRM_QUOTES,MM_MATMASTER,PM_EQUIPMASTER,PP_DWNTIME_LOG,PP_PRODORD,SD_SALESORD}/`. They exist solely to make `start.sh --seed` work in the template; a customer fork replaces them with the customer's real source-table migrations.
9. Pull from upstream periodically. Conflicts mainly in `customer/` registry files. Customer-specific migration files don't conflict with upstream — they live under directories the template doesn't ship.

### Agent evals

Behavioural tests for the chat agent. **Local only — never run in CI.** They call the real model against the locally-configured data, so they have a real cost and rely on local seed/state.

**Layout — split between template and customer carveout, all under `tests/evals/`** (evals are test code, not production code):

- `tests/evals/_case.py` — `EvalCase` dataclass (template). Owned upstream; do not edit in forks.
- `tests/evals/_runner.py`, `_report.py`, `conftest.py`, `test_evals.py`, `test_zz_report.py` — runner, fixtures, HTML report (template). `_runner.py` builds the agent through the same DI path as production (`get_agent_deps()`, `get_prompt_loader()`), so evals exercise the real `LocalFileSystem`, `DuckDBWarehouse`, `FilePromptLoader`, tools, and model. `test_zz_report.py` runs last (alphabetical filename ordering) and writes `tests/evals/report.html` from a module-level results buffer.
- `tests/evals/customer/` — case definitions (customer carveout). One file per toolbox (`sales.py`, `production.py`, ...) plus `shared.py` for cross-toolbox behaviour. `__init__.py` aggregates `ALL_CASES`.

**Convention: one example case per toolbox in the template.** Forks extend with as many cases as they need. The pre-commit hook `customer-config` validates that every `Toolbox` value has at least one case.

**Each `EvalCase` combines:**
- **Deterministic checks** — `expected_tool_calls`, `forbidden_tool_calls`, `response_contains` (substring), `response_regex`. Cheap, run first; failure here skips the judge.
- **LLM-as-judge** (optional) — set `judge_rubric` for open-ended outputs (recommendations, drafted emails, refusals). The judge is just another `Agent` call against the same model resolver as the main agent, returning a structured `JudgeVerdict { score: float, reasoning: str }`. Score must meet `judge_threshold` (default 0.7).

**No stubs anywhere.** Every component is the production component — filesystem, warehouse, prompts, tools, model, judge. If `data/datasets/` is empty locally, cases will fail loudly. That's intentional.

**Run manually:**
```bash
uv run python scripts/seed.py        # if not already seeded
uv run pytest tests/evals -v
open tests/evals/report.html
```

**Pre-commit hook** (`agent-evals`): fires `uv run pytest tests/evals -q`, but **only when a file under `backend/prompts/*.md` is staged**. The HTML report is gitignored.

**Adding cases:**
1. Append an `EvalCase(...)` to the relevant file in `tests/evals/customer/`.
2. Reference real data that's actually in the local `data/datasets/` views and `data/documents/` files — assertions like `expected_tool_calls=["execute_sql"]` and judge rubrics that demand specific names/numbers from the seeded universe.

**Adding a toolbox** (in addition to the toolbox-onboarding steps elsewhere in this doc):
1. Create `tests/evals/customer/{toolbox}.py` with at least one `EvalCase`.
2. Aggregate it into `ALL_CASES` in `tests/evals/customer/__init__.py`.
3. `uv run python scripts/check_customer_config.py` must show "Eval coverage per toolbox" green.

**Forking checklist for evals:**
- Replace example cases with cases grounded in the customer's data and prompts. Generic cases (e.g. "draft a follow-up email to <Customer>") need real customer/account names from the fork's seeded data.
- Keep one-case-per-toolbox as a floor; add as many real-world use cases as the team needs to feel confident shipping prompt changes.
- Never commit `tests/evals/report.html` (gitignored).

### Data layer

- **PostgreSQL** = platform data (conversations, task outputs, auth). Shared schema.
- **DuckDB** = customer data (read-only, ingested). Schema from data + SQL views.
- Delta Lake tables in `data/datasets/`. SQL views in `data/datasets/views/*.sql`.

## Authentication (Supabase Auth)

Auth is delegated to Supabase. The backend never sees passwords — it verifies the JWT in the `Authorization: Bearer ...` header against Supabase's JWKS and upserts a row in our local `users` table on every authenticated request. `users.role` (`admin` | `regular`) is the source of truth for authorization, not Supabase metadata.

**Project setup (one-time, per Supabase project):**
- In Dashboard > Project Settings > API > JWT Settings, enable an asymmetric signing key (ES256 or RS256). The HS256 default is rejected by the backend.
- In Dashboard > Authentication > Policies, set **minimum password length ≥ 12**, enable **leaked password protection** (HIBP), and confirm sign-in **rate limits** are on. The frontend enforces a 12-char floor too, but the Supabase project policy is the real gate — keep them in sync.
- Consider requiring **MFA (TOTP)** for any user that gets `role='admin'`. The app treats admin and regular logins identically; password-only is too thin a defense for the invite/delete/impersonate surface.
- The frontend uses the **anon** (publishable) key. The backend uses the **service-role** key for the admin-invite API only.

**Backend env vars** (`env.template`):
- `SUPABASE_URL` — project URL.
- `SUPABASE_SERVICE_ROLE_KEY` — service-role key. Backend-only; never expose to the browser.
- `INITIAL_ADMIN_EMAILS` — comma-separated emails that get `role='admin'` on first login. All other invitees become `'regular'`.
- `SITE_URL` — frontend URL used as the redirect target in invite links (e.g. `http://localhost:5173`).

JWKS URL, JWT issuer, and JWT audience are derived from `SUPABASE_URL`. No overrides in production.

**Frontend env vars** (`frontend/.env.template`):
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

**First admin bootstrap:**
1. Set `INITIAL_ADMIN_EMAILS=you@example.com` in `.env`.
2. In Supabase Dashboard > Authentication > Users, click "Add user" and set a temporary password.
3. Log in via the app. The `users` row is created with `role='admin'` because the email matches `INITIAL_ADMIN_EMAILS`.

**Inviting more users:**
- Admins navigate to `/admin` in the app.
- Submit an email — backend mints a Supabase invite link via the admin API and returns it to the browser. The admin copies and pastes it manually (no SMTP wired).
- Invitee opens the link, sets a password, lands on `/`.
- **Limitation:** the role chosen in the invite form is advisory. New users are always `regular` unless their email is in `INITIAL_ADMIN_EMAILS`. To promote later, update the `users` table directly.

**Conversation isolation:** every conversation row has a `user_id`. All chat/list/get endpoints filter by `user.id` from the JWT — users can only see their own conversations. Existing rows from before the migration have `user_id = NULL` and are inaccessible.

## Testing

Test **business logic** at the use-case entry point — the function a route
handler calls (`run_compaction`, `execute_sql`, `generate_signals`, etc.).
Routes themselves must stay thin (`parse + call core + return`); if a route
has logic worth testing, move it into a core use-case.

For collaborators in `core/interfaces/*`, prefer in this order:

1. **The real implementation against an in-memory or temp backing store.**
   - `ConversationRepository` against in-memory SQLite — see the
     `conversation_repo` and `repo_factory` fixtures in `tests/conftest.py`.
   - `LocalFileSystem` against `tmp_path`.
   - `LocalTaskQueue` as-is.
   - `DuckDBWarehouse` against a fixture views directory.
2. **A hand-written fake** under `tests/fakes/` only when no cheap real
   backing exists (LLM clients, external HTTP APIs). See
   `tests/fakes/agent.py` (`FakeSummarizationAgent`) for the pattern.
3. **`AsyncMock(spec=Interface)`** only for stateless one-shot collaborators
   (send email, publish event). Always pass `spec=`.

**Never `MagicMock`/`AsyncMock` an interface from `core/interfaces/*`.**
Mocks let you set up impossible states, and the orchestration cost compounds
fast on stateful collaborators. **Never `assert_called_with`.** Assert on
observable behavior — return values, repo state after the call, fake state.

The test suite **never makes real LLM calls**. Real-model behavior belongs
in `tests/evals/`, which is local-only and never runs in CI.

**Do write:**
- One test per distinct use-case behavior: happy path + each failure mode
  (empty repo, missing file, forbidden input, wrong role, cross-user access,
  external API raises). Not one per branch.
- Pure-function tests **only** when the function enforces a silent invariant
  with a high-cost regression: security gates (`is_read_only`), write
  protection, auth, path traversal, parsing untrusted/LLM-produced input
  with subtle structure (see `TestPruneToolOutputsProcessor` in
  `tests/test_compaction.py`).

**Don't write:**
- HTTP / route tests (the route is too thin to be worth it).
- Pure-function tests for trivial transforms (`len(text) // 4`, simple
  formatters, getters).
- DI wiring tests, snapshot tests, tests asserting on LLM output content.
- Tests that re-cover what a use-case test already covers.

**Adding a new interface in `core/interfaces/`?** Add the in-memory
implementation or fake in the same change so callers can test against it.

**Frontend:**
- Component tests **only** when there's real local logic — forms,
  conditional rendering, computed displays (`SignalsDashboard` stats math,
  archive toggle). Mock at the `lib/queries.ts` boundary only.
- If the mock surface dwarfs the assertion (mocking `useChat`,
  `DefaultChatTransport`, `streamdown`, etc.), **delete the test** and cover
  the flow with Playwright instead.
- 3–5 Playwright smokes for critical user flows, run against the full stack.
- No snapshot tests. No tests of shadcn / AI Elements internals.

## Theme

Global color theme in `frontend/src/index.css` with light/dark mode support. Toggle via ThemeProvider context.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Security audit, threat model, OWASP → invoke cso
- QA, test the site, find bugs → invoke qa
