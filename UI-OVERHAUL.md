# UI Overhaul: Toolbox-First Navigation

*2026-04-10*

## The Problem with the Current UI

The current UI has two navigation items (Signals, Chat) with a toolbox dropdown that switches context (Sales, Production). The toolbox is a filter on a generic view. This means every use case looks the same and the UI can't be tailored to specific customer problems.

## The New Model: Toolbox as Workspace

The toolbox becomes the primary navigation. Each toolbox is a purpose-built workspace for a specific problem domain, with its own views and layout. The shell (sidebar, auth, theme) is shared scaffolding. What's inside each toolbox is configured per customer.

### Current sidebar

```
Signals
Chat
─────────
TOOLBOX: [Sales ▾]
```

### New sidebar

```
Sales
  Chat
  Signals
  Pipeline        ← custom view
Production
  Chat
  Signals
  OEE Dashboard   ← custom view
Support
  Chat
  Ticket Queue    ← custom view
```

Each toolbox has its own set of views. Some views are shared components (Chat, Signals). Some are customer-specific (Pipeline, OEE Dashboard, Ticket Queue). The sidebar entries are customer-configured, not hardcoded categories.

## Architecture Layers

### 1. Shell (shared, never customer-specific)

Sidebar navigation, auth, theme toggle, responsive layout. This is the platform scaffolding. It reads a toolbox configuration and renders the sidebar accordingly.

### 2. UI Components (shared library)

Reusable components that can appear in any toolbox:

- **Chat**: always hits the same `/api/chat` endpoint. Configured per-toolbox with different tools and prompts, but the component and API contract are identical.
- **Signals**: same signal feed component, filtered by toolbox context. Displays signals that were generated for the active toolbox.
- Standard widgets: stat cards, tables, charts.

These are built once, used everywhere.

### Signals and background tasks

Signals follow the same template/customer split as tools:

- **Template (shared)**: the task queue, signal repository, signal entity, the mechanism that runs background tasks on a schedule, and the SignalsDashboard component that displays them. All of this lives in `backend/core/` and `backend/infrastructure/`.
- **Customer code**: the actual signal generators and background agents. A Sales toolbox might have `detect_declining_accounts.py` and `detect_stalled_quotes.py`. A Support toolbox might have `detect_sla_breaches.py` or a "draft response" agent. These live under `backend/customer/tasks/` and are registered per toolbox in `TOOLBOX_TASKS`.

Each generator writes signals tagged with the toolbox they belong to. The SignalsDashboard in the Sales toolbox filters to sales signals. The one in Support filters to support signals. Same component, toolbox-scoped data.

Any new background agent or task developed for a customer use case naturally scopes to the toolbox it serves. New signal types, new agent workflows, new scheduled tasks all live under `backend/customer/tasks/` and are registered with the toolbox they belong to via `TOOLBOX_TASKS`.

### 3. Toolbox Pages (per-customer, per-domain)

Each toolbox view is a page that composes shared components with custom views. For example:

- `Sales > Chat` renders the Chat component configured with sales tools and prompts.
- `Sales > Pipeline` is a fully custom view built for that customer's quote tracking workflow.
- `Support > Chat` renders the same Chat component but configured with support tools and prompts.

### 4. The Toolbox Enum (shared contract between frontend and backend)

The toolbox is a two-layer hierarchy: customer-specific (different customers have different toolboxes) and toolbox-specific (each toolbox configures different tools and prompts). To make this work, frontend and backend need to agree on toolbox identifiers.

Each customer defines a toolbox enum (just string constants) that both sides reference. It's customer-specific, so it lives in the customer carveout on both sides.

```typescript
// frontend/src/customer/toolboxes.ts
export enum Toolbox {
  Sales = 'sales',
  Support = 'support',
}
```

```python
# backend/customer/toolboxes.py
from enum import StrEnum

class Toolbox(StrEnum):
    SALES = "sales"
    SUPPORT = "support"
```

The frontend sends the toolbox ID with each chat request. The backend receives it as a string, validates against the enum, and uses it to pick the right tools and fetch the right prompt. The template code handles requests generically: it takes a `toolbox` parameter, looks up tools from the customer registry, fetches the prompt via the PromptLoader. The template never hardcodes toolbox names.

### 5. Agent Configuration (per-toolbox, customer-controlled)

Each toolbox configures the AI agent differently:

- **Tools**: which backend tools are available to the agent. Sales chat gets `query_installed_base`, `query_quotes`, `cross_sell_analysis`. Support chat gets `query_tickets`, `search_knowledge_base`.
- **Prompts**: system prompt, persona, instructions. Sales agent knows about spare parts, pricing, customer accounts. Support agent knows about ticket history, FAQ, troubleshooting.

Tools flow through Python imports (customer code in the repo). Prompts flow through the existing `PromptLoader` interface (blob storage in prod, filesystem fallback in dev). Both are customer- AND toolbox-specific.

### 6. Backend Customer Carveout (single directory)

The existing backend architecture (`api/`, `core/`, `infrastructure/`) stays as shared template code. All customer-editable Python code lives under a single `backend/customer/` directory. This is the one place template and customer code meet, and it's where all the customer-specific logic lives.

```
backend/
  api/                        ← template
  core/                       ← template
  infrastructure/             ← template (including PromptLoader)
  prompts/                    ← filesystem fallback: demo prompts in template,
                                customer prompts in fork (loaded at runtime,
                                not imported as Python)
  customer/                   ← the single customer carveout
    __init__.py               ← exports the stable contract symbols
    toolboxes.py              ← Toolbox enum
    tools/
      __init__.py             ← exports TOOLBOX_TOOLS: dict[Toolbox, list[Tool]]
      execute_sql.py          ← template default, can be kept or replaced
      read_file.py            ← template default
      query_installed_base.py ← customer-added
      cross_sell_analysis.py  ← customer-added
      query_tickets.py        ← customer-added
    tasks/
      __init__.py             ← exports TOOLBOX_TASKS: dict[Toolbox, list[Task]]
      detect_stalled_quotes.py
      detect_sla_breaches.py
```

The stable contract from the template's perspective is just a few symbols imported from `backend.customer`:

```python
# backend/core/agents/chat_agent.py  (template, never changes)
from backend.customer import TOOLBOX_TOOLS
from backend.customer.toolboxes import Toolbox

def build_agent(toolbox: Toolbox, prompt: str):
    return Agent(
        model=...,
        tools=TOOLBOX_TOOLS[toolbox],
        system_prompt=prompt,
    )
```

```python
# backend/customer/__init__.py  (customer controls)
from .tools import TOOLBOX_TOOLS
from .tasks import TOOLBOX_TASKS
from .toolboxes import Toolbox

__all__ = ["TOOLBOX_TOOLS", "TOOLBOX_TASKS", "Toolbox"]
```

```python
# backend/customer/tools/__init__.py  (customer controls)
from backend.customer.toolboxes import Toolbox
from .execute_sql import execute_sql_tool
from .query_installed_base import query_installed_base_tool
from .cross_sell_analysis import cross_sell_analysis_tool
from .query_tickets import query_tickets_tool

TOOLBOX_TOOLS = {
    Toolbox.SALES: [execute_sql_tool, query_installed_base_tool, cross_sell_analysis_tool],
    Toolbox.SUPPORT: [execute_sql_tool, query_tickets_tool],
}
```

### 7. Prompts (customer-specific AND toolbox-specific, loaded at runtime)

Prompts don't live in the Python import carveout because they're not Python. They're markdown loaded at runtime through the `PromptLoader` interface.

- **Production**: blob storage, per-customer container. Already customer-specific by virtue of storage location.
- **Development**: filesystem fallback reading from `backend/prompts/`. In the template repo, this contains demo prompts. In a customer fork, it contains that customer's prompts for local dev.

The PromptLoader interface extends to take a toolbox identifier:

```python
# backend/core/interfaces/prompt_loader.py  (template)
from backend.customer.toolboxes import Toolbox

class PromptLoader(Protocol):
    def load(self, toolbox: Toolbox) -> str:
        """Load the composed system prompt for the given toolbox."""
        ...
```

#### Prompt composition: two files

The composed system prompt is built from exactly two files per toolbox:

1. **`system.md`** — customer-specific, shared across all toolboxes. The agent's persona, identity, company context, operational guidelines. This replaces the current `identity.md` + `user.md` + `operations.md` split (collapsed to one file). One copy per customer, in their blob container (or local `backend/prompts/system.md` for dev).

2. **`<toolbox>.md`** — customer-specific AND toolbox-specific. The persona, knowledge, and instructions for THIS toolbox. `sales.md` for the Sales toolbox, `support.md` for Support, etc.

`PromptLoader.load(toolbox)` fetches both files, composes them (system.md first, toolbox.md second), and returns the combined string. Neither file lives in `backend/customer/` because neither is Python. Both are loaded as data at runtime through the existing infrastructure abstraction.

The filesystem fallback directory layout:

```
backend/prompts/
  system.md          ← customer persona + company context
  sales.md           ← Sales toolbox instructions
  support.md         ← Support toolbox instructions
```

No Python imports means no merge conflicts from prompts on template pulls. The template ships with demo prompts in `backend/prompts/`; the customer fork replaces them with real content (or configures blob storage in prod).

### What lives in `backend/customer/`, what doesn't

| Thing | Where | Why |
|---|---|---|
| Tools | `backend/customer/tools/` | Python code, imported at startup |
| Background tasks | `backend/customer/tasks/` | Python code, imported at startup |
| Toolbox enum | `backend/customer/toolboxes.py` | Python code referenced everywhere |
| Prompts | `backend/prompts/` (filesystem) or blob storage | Not Python, loaded at runtime |
| DuckDB views (ontology) | `data/datasets/views/` | Not Python, loaded at runtime |
| Ingested Delta tables | `data/datasets/` | Not Python, loaded at runtime |

## Integration Details

### How the toolbox ID flows from frontend to backend

The toolbox travels with the chat request as a typed field. Best practice for a TypeScript frontend ↔ FastAPI backend:

- The backend defines a Pydantic model for the chat request body that includes `toolbox: Toolbox` (the backend's `StrEnum`). FastAPI validates the value against the enum automatically and returns a 422 if the frontend sends an unknown toolbox.
- The frontend sends the toolbox ID in the request body, not as a header. Headers are for metadata; toolbox is a domain parameter.
- The Vercel AI SDK's `DefaultChatTransport` supports a `body` option for attaching extra fields to every chat request. The Chat component passes the toolbox through this mechanism.

```python
# backend/api/models/chat.py (template)
from pydantic import BaseModel
from backend.customer.toolboxes import Toolbox

class ChatRequest(BaseModel):
    messages: list[...]  # whatever Vercel AI SDK message shape
    toolbox: Toolbox
```

```typescript
// frontend/src/customer/sales/SalesChat.tsx
import { useChat, DefaultChatTransport } from '@ai-sdk/react'
import { Toolbox } from '../toolboxes'

export function SalesChat() {
  const chat = useChat({
    transport: new DefaultChatTransport({
      api: '/api/chat',
      body: { toolbox: Toolbox.Sales },
    }),
  })
  return <Chat {...chat} />
}
```

The `Toolbox` enum is the contract. Pydantic validates on the backend, TypeScript enforces on the frontend. Invalid values fail loudly at the boundary.

### How the Chat component receives its toolbox

The Chat component itself is toolbox-agnostic. It's the customer toolbox pages that bake the toolbox into the transport and hand a configured chat interface to the shared component. `SalesChat` is a thin wrapper around the shared `Chat` that passes `Toolbox.Sales`. `SupportChat` is the same wrapper with `Toolbox.Support`. The shared `Chat` component never needs to know about specific toolboxes.

This keeps the shared component simple and pushes toolbox-awareness to the customer layer, which is where it belongs.

### Signals are toolbox-scoped

Signals already have a `toolbox` column in the database (`backend/infrastructure/db/models/signal.py`) with an index on it. The schema is ready. The `SignalsDashboard` component in each toolbox queries signals filtered by that toolbox. One dashboard component, toolbox-scoped queries. No schema changes needed.

Background tasks that generate signals should write `toolbox=Toolbox.SALES` (or whichever) when creating signal rows. The task list per toolbox (`TOOLBOX_TASKS[Toolbox.SALES]`) makes this natural: each task in a toolbox's list produces signals tagged with that toolbox.

### The customer config consistency check

The customer carveout has several things that must stay internally consistent: the Python and TypeScript toolbox enums must match, every toolbox must have tool/task registry entries, every toolbox must have a prompt file, and the toolbox pages referenced in the frontend registry must actually exist. None of this is enforceable by the type system alone because the enum is split across two languages and the prompt files live outside the codebase.

A single Python script at `scripts/check_customer_config.py` handles all of this. It runs as a pre-commit hook, in CI, and on demand during development.

#### What it checks

**Enum parity.** Parses `backend/customer/toolboxes.py` (by importing) and `frontend/src/customer/toolboxes.ts` (textually), compares enum names and string values. Fails if either side has a toolbox the other doesn't.

**Tool and task registry completeness.** Imports `TOOLBOX_TOOLS` and `TOOLBOX_TASKS` from `backend.customer`. Verifies every toolbox in the enum has an entry in both dicts. Warns if `TOOLBOX_TOOLS` has an empty list for some toolbox (a toolbox with no tools is probably a mistake).

**Frontend toolbox registry completeness.** Parses `frontend/src/customer/toolboxes.ts` for the `toolboxes` array. Verifies every toolbox in the enum has a matching entry. Verifies the component files referenced in each entry actually exist on disk.

**Prompt file presence, environment-aware.** Reads the same config the app uses to determine where prompts live:

- If the prompt storage config points at local filesystem (`backend/prompts/`), check that `system.md` and `<toolbox>.md` exist for each toolbox in the enum.
- If it points at blob storage (via env vars), list the container and check for the same files there.

This makes the check match the actual runtime behavior of whichever environment the developer has configured. Local dev with filesystem? Check the filesystem. Staging with blob storage? Check blob storage. Same script, different target.

#### DevX requirements

- **Fast.** Filesystem checks should take under a second. Blob storage checks a few seconds. Pre-commit hook speed matters.
- **Clear output.** State facts, don't assume intent. The developer knows whether they were adding or removing a toolbox:
  ```
  ✗ Toolbox mismatch: `production`
    Present in:  backend/customer/toolboxes.py
    Missing in:  frontend/src/customer/toolboxes.ts

  ✗ Missing prompt file for toolbox `production`
    Expected:    backend/prompts/production.md (filesystem backend active)
  ```
  No "fix: add X" suggestions. If the developer was removing `production`, the right fix is to remove it from the backend enum, not add it to the frontend. The script only reports what's inconsistent, not how to resolve it.
- **Green checkmarks for what passed, red X's for what failed.** Summary at the end counts how many of each.
- **Bypassable.** Pre-commit should always respect `--no-verify` for mid-refactor commits.
- **Runnable standalone.** `uv run scripts/check_customer_config.py` from the project root, plus an npm script alias like `npm run check:customer` that shells out to the same script.
- **Used in CI** as a required check on every PR.

#### Why this is better than just an enum sync check

A dumb enum diff only catches "I changed one side but not the other". The full consistency check catches the whole class of "I added a toolbox but forgot to wire it up somewhere" errors: missing tool registry entries, missing prompt files, missing toolbox page components, broken import paths in the registry. All of these are common mistakes when onboarding a new toolbox, and all of them fail silently at runtime without this check. One script, one run, all the errors surface at once.

## Project Structure: Template vs. Customer

fulcrum-chat is a template project. Customer deployments are plain git forks that pull updates from the template upstream. The file system is organized so template updates and customer-specific code touch different files and merges stay manageable.

### The single-carveout model

Both frontend and backend have exactly one directory where customer code lives:

- `frontend/src/customer/` — toolbox registry, custom pages, customer components
- `backend/customer/` — tools, tasks, toolbox enum

That's it. Everything outside those directories is template code. The template ships with working default implementations inside `customer/` so the repo runs out of the box. When you fork for a customer, you edit `customer/` to match that customer's needs.

### Directory layout

```
fulcrum-chat/
  frontend/
    src/
      components/           ← shared UI components (Chat, Signals, widgets) — template
      shell/                ← sidebar, layout, auth, theme — template
      customer/             ← the customer carveout
        toolboxes.ts        ← Toolbox enum + toolbox registry
        sales/
          SalesChat.tsx
          Pipeline.tsx
        support/
          SupportChat.tsx
          Tickets.tsx
  backend/
    api/                    ← template
    core/                   ← template (agents, entities, interfaces)
    infrastructure/         ← template (db, data warehouse, prompt loader)
    prompts/                ← filesystem fallback for prompt loader (data, not code)
    customer/               ← the customer carveout
      __init__.py
      toolboxes.py          ← Toolbox enum
      tools/
        __init__.py         ← exports TOOLBOX_TOOLS
        execute_sql.py
        query_installed_base.py
        cross_sell_analysis.py
        query_tickets.py
      tasks/
        __init__.py         ← exports TOOLBOX_TASKS
        detect_stalled_quotes.py
  data/
    datasets/               ← customer-specific ingested data + views
      views/
```

### The default implementation

The template ships with a working default implementation inside `customer/`. It serves two purposes:

1. **Working demo.** The template repo runs out of the box with demo tools, demo prompts, and a demo toolbox. You can pitch Fulcrum without any customer-specific code.
2. **Reference starting point.** When forking for a new customer, you start with the default implementation and edit it toward what that customer needs.

### How toolboxes are registered on the frontend

The frontend `customer/toolboxes.ts` exports the `Toolbox` enum plus the toolbox registry. This is code, not JSON config, because it references actual React components.

```typescript
// frontend/src/customer/toolboxes.ts
import { SalesChat } from './sales/SalesChat'
import { Pipeline } from './sales/Pipeline'
import { SupportChat } from './support/SupportChat'
import { Tickets } from './support/Tickets'

export enum Toolbox {
  Sales = 'sales',
  Support = 'support',
}

export const toolboxes = [
  {
    id: Toolbox.Sales,
    label: 'Sales',
    icon: 'TrendingUp',
    views: [
      { id: 'chat', label: 'Chat', component: SalesChat },
      { id: 'pipeline', label: 'Pipeline', component: Pipeline },
    ],
  },
  {
    id: Toolbox.Support,
    label: 'Support',
    icon: 'Headphones',
    views: [
      { id: 'chat', label: 'Chat', component: SupportChat },
      { id: 'tickets', label: 'Tickets', component: Tickets },
    ],
  },
]
```

The shell imports `toolboxes` from `customer/toolboxes.ts` and renders the sidebar and routes from it. When the Chat component sends a request, it attaches the active toolbox ID. The backend receives that ID as a string, validates against its own `Toolbox` enum, and uses it to pick tools and fetch the right prompt.

### Pulling template updates

The rule: **template code never imports from customer directories. Customer code imports from template.**

When you pull updates from the template repo into a customer fork:

- **Template changes touch template files**: `frontend/src/components/`, `frontend/src/shell/`, `backend/api/`, `backend/core/`, `backend/infrastructure/`. Pulls bring those changes in cleanly because the customer fork doesn't edit them.
- **Customer changes touch `customer/` files**: `frontend/src/customer/` and `backend/customer/`. Pulls don't touch those paths unless the template itself edited its default implementation in `customer/`.
- **Conflicts only happen when template and customer both edit the same file**. This is most likely in `backend/customer/tools/__init__.py`, `backend/customer/tasks/__init__.py`, and `frontend/src/customer/toolboxes.ts` — the files that list things.

### Minimizing conflicts in `customer/`

The `customer/` directory is the only place both sides might edit the same files. The discipline to keep this manageable:

- **Add new files, rarely edit existing ones.** A new template default tool ships as a new `.py` file. A customer tool is a new `.py` file. Two new files never conflict.
- **Registry files (`__init__.py`, `toolboxes.ts`) are the conflict surface.** These list things by name. When both sides add entries, you get a merge conflict. The conflict is usually trivial to resolve (keep both entries), but it's work.
- **Template should avoid editing its `customer/` defaults once shipped.** Treat the default implementation as a stable reference. Bug fixes or new features go into new files, not edits to existing ones.
- **If a customer needs to change a default tool's behavior, add a new tool instead of editing the original.** The unused default stays around receiving template updates cleanly. If it's truly obsolete, delete it in the customer fork.

Tests catch semantic breakage from template pulls: if a shared interface changes in a way that silently breaks customer code, the test suite should fail before production.

### Data layer

Two databases with a clean split:

- **PostgreSQL** = platform data. Conversations, signals, ingestion logs, auth. Shared schema, template code. Same for every customer. Lives in `infrastructure/db/`.
- **DuckDB** = customer data. Whatever was ingested (ERP exports, CRM dumps, sensor data, etc.). Always customer-specific. Read-only: customer tools query it via the data warehouse interface with SQL.

This is the starting point. If a customer feature needs to write persistent state (e.g. ticket status, quote approvals), that would likely go into PostgreSQL with customer-specific tables and migrations under `backend/customer/`. Cross that bridge when we get there.

### Ontology: how the customer data schema is formed

The DuckDB schema is built in two layers:

1. **Raw tables.** Ingestion writes customer data as Delta Lake tables into `data/datasets/`. DuckDB materializes these as `_raw_<name>` tables automatically on startup/refresh. The schema comes directly from the source data (ERP exports, CRM dumps, etc.).

2. **SQL views.** View definitions in `data/datasets/views/*.sql` reshape the raw tables into a queryable schema. These views are the "ontology": they rename columns, join tables, add descriptions, and present the data in terms the agent and users can work with.

```
data/datasets/
  customers/              ← Delta Lake table (raw ingested data)
    _delta_log/
  orders/                 ← Delta Lake table
    _delta_log/
  views/
    customers.sql         ← CREATE OR REPLACE VIEW customers AS SELECT ...
    customer_purchase_trends.sql
    quotes.sql
    sales_orders.sql
    products.sql
    machines.sql
    downtime_events.sql
    production_orders.sql
```

The views are the customer-specific part. When onboarding a new customer, the workflow is:

1. Ingest the customer's real data exports (ERP, CRM, etc.)
2. Inspect the raw table schemas that result
3. Write SQL views that reshape the raw data into a meaningful ontology: what are the entities, how they relate, what columns matter, what names make sense
4. Iterate on the views as understanding of the customer's data deepens

This is done together with Claude Code, using the real data schema and business context from the customer to define the views. The views are the primary artifact of the "ontology mapping" phase of a customer engagement.

## What Changes When You Add a New Use Case

| What you touch | Where |
|---|---|
| Backend tools | `backend/customer/tools/` + add to `TOOLBOX_TOOLS` |
| Prompts | Blob storage (or `backend/prompts/` for local dev) |
| Toolbox enum | `backend/customer/toolboxes.py` + `frontend/src/customer/toolboxes.ts` |
| Signal generators / background tasks | `backend/customer/tasks/` + add to `TOOLBOX_TASKS` |
| DuckDB views (ontology) | `data/datasets/views/` |
| Toolbox page | `frontend/src/customer/` (compose shared components) |
| Toolbox registry | `frontend/src/customer/toolboxes.ts` |
| PostgreSQL tables (if needed) | `backend/customer/` (cross that bridge later) |

What you don't touch: the chat API, the Chat component, agent orchestration, auth, the shell, the prompt loader interface.

## What Changes When You Onboard a New Customer

1. Fork the template repo into a new customer repo (plain git fork, upstream points at template).
2. Edit `backend/customer/` and `frontend/src/customer/` to match the customer's toolboxes, tools, and views. Use the default implementation as a starting point.
3. Upload customer-specific prompts to blob storage, or populate `backend/prompts/` for local dev.
4. Ingest customer data into `data/datasets/` and write SQL views in `data/datasets/views/` to define the ontology.
5. Pull from upstream periodically to get template updates. Resolve merge conflicts in `customer/` registry files when they come up.

## Example: Glaston

```
Sales
  Chat        → agent with installed base, cross-sell, quote tracking tools
  Signals     → sales signals (declining accounts, stalled quotes)
  Pipeline    → custom quote pipeline view

Support
  Chat        → agent with ticket history, FAQ, knowledge base tools
  Signals     → support signals (SLA breaches, recurring issues)
  Tickets     → custom ticket queue view
```

## Example: Tamtron

```
Sales
  Chat        → agent with product catalog, pricing, quotation tools
  Signals     → sales signals

Support
  Chat        → agent with support history, FAQ lookup, draft response tools
  Signals     → support signals (ticket volume, response time)
  Tickets     → custom ticket queue with AI-drafted responses
```

## TODO: CLAUDE.md must document all of this

This architecture is challenging to keep track of in practice. It spans frontend, backend, data layer, deployment model, and merge-conflict discipline. A new contributor (or future-us six months from now) needs a clear, single-source explanation of how it all fits together. **CLAUDE.md is that source.** Without it, the nuances of template vs. customer code, the import contracts, and the "add don't edit" discipline will get lost and the architecture will erode.

When implementing this overhaul, CLAUDE.md must be updated to cover:

### Template vs. customer code
- The single-carveout model: one `customer/` directory per side (frontend and backend)
- What lives in `customer/` (Python tools, tasks, toolbox enum, React pages) and what doesn't (prompts via PromptLoader, DuckDB views as data files)
- The stable import contract: template imports `TOOLBOX_TOOLS`, `TOOLBOX_TASKS`, `Toolbox` from `backend.customer` and nothing else
- The "add new files, rarely edit existing ones" discipline for minimizing merge conflicts
- Where conflicts are expected (registry `__init__.py` and `toolboxes.ts`) and how to resolve them

### Toolbox architecture
- What a toolbox is: a customer-specific, problem-focused workspace with its own views, tools, and prompt
- The `Toolbox` enum as shared contract between frontend and backend
- How toolbox ID flows from the frontend through the chat request to the agent
- How `TOOLBOX_TOOLS` and `TOOLBOX_TASKS` dicts scope things per toolbox
- How the frontend sidebar and routes are generated from `customer/toolboxes.ts`

### Prompts and the PromptLoader
- Prompts are NOT in the Python import carveout. They're data loaded at runtime.
- Blob storage in prod, `backend/prompts/` filesystem in dev
- The PromptLoader interface takes a `Toolbox` and returns a composed prompt
- How identity/operations headers compose with toolbox-specific content

### DuckDB data layer and ontology
- Ingestion writes Delta Lake tables into `data/datasets/`
- DuckDB materializes them as `_raw_<name>` automatically
- SQL views in `data/datasets/views/*.sql` define the ontology (rename, join, describe)
- The onboarding workflow: ingest real data → inspect raw schemas → write views with Claude Code using customer business context
- Views are the primary artifact of the "ontology mapping" phase of a customer engagement

### Data split between PostgreSQL and DuckDB
- PostgreSQL = platform data (conversations, signals, auth), shared schema, template code
- DuckDB = customer data (read-only, ingested), schema from the data itself plus SQL views
- Future: customer-specific PostgreSQL tables would go under `backend/customer/` with their own migrations

### Adding a new use case
- A concrete walkthrough: "how to add a new tool to the Sales toolbox" end-to-end
- A concrete walkthrough: "how to add a new toolbox" end-to-end
- What files you touch, in what order

### Forking for a new customer
- The workflow: git fork, edit `customer/`, upload prompts, ingest data, write views
- How to pull upstream template updates and handle conflicts

Currently `CLAUDE.md` covers PostgreSQL and file tools only. This is a massive documentation gap for an architecture this nuanced. Budget time to write it properly when implementing.

## Future: MCP for Tool Modularity

The natural evolution is providing toolsets through MCP (Model Context Protocol), making the agent fully generic and tool-agnostic. The agent becomes a shell that receives its capabilities entirely through MCP tool servers. Combined with customer-specific UI, this would make onboarding a new domain purely configuration.

Not needed now. The current approach (tools directory + prompt templates + shared UI components) is the right level of modularity for the stage we're at.
