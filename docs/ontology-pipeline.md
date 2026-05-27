# Ontology pipeline

End-to-end map of how a customer ontology gets built. Phases, handoffs, terms. The detail for each phase lives in its skill.

For the conceptual foundation (what an ontology *is*), read [ontology.md](ontology.md).

## Pipeline at a glance

```
┌─────────────┐   ┌────────────────┐   ┌─────────────────┐   ┌────────────────┐
│ ingest-data │ → │ build-ontology │ → │ extend-ontology │ → │ review-ontology│
└─────────────┘   └────────────────┘   └─────────────────┘   └────────────────┘
```

Four skills, executed in order. Each produces its own artifacts; humans review between every pair.

| Phase | Skill | Produces |
|---|---|---|
| 1 | `ingest-data` | Raw-table schema migrations, raw Delta tables, column-usage CSVs, `INGEST_NOTES.md` |
| 2 | `build-ontology` | Entity + event views, prompt updates, `ONTOLOGY_NOTES.md` |
| 3 | `extend-ontology` | Recipes, task stubs, derived-table migrations, derived tables, wrapping views, semantic-search tools |
| 4 | `review-ontology` | `ONTOLOGY_REVIEW.md` findings report |

The pipeline is iterative. After review you typically loop back to `extend-ontology` (or `build-ontology`) to fix findings, then re-review.

Each skill checks its preconditions before doing work. If the prior phase's outputs aren't present, the skill stops and points at the phase that should run first. On re-runs, each skill detects existing outputs and treats the run as additive — it reads prior notes, lists what's already there to the user, and does not overwrite. Targeted fixes (renaming a column, tweaking a CASE, editing one recipe) are direct file edits, not skill invocations.

The breadcrumb between Phase 2 and Phase 3 is explicit: `build-ontology` records dimensions it noticed but couldn't model under `## Derived dimensions deferred to extend-ontology` in `ONTOLOGY_NOTES.md`. `extend-ontology` reads that section first.

## Terms

**Raw table** — Delta table at `data/datasets/<NAME>/`, faithful to a customer source file. Read by DuckDB as `_raw_<NAME>`. Never seen by the agent.

**View** — DuckDB SQL view at `data/datasets/views/<name>.sql`. The agent's interface to the data.

**Entity view** — view whose rows are real-world things (customers, machines, parts). Stable PK, one row per thing.

**Event view** — view whose rows are time-stamped facts (orders, service visits). FK references entity views.

**Derived dimension** — a property the agent needs that isn't in the raw data, produced by computation. Four classes: SQL-now / Precomputed-deterministic / Precomputed-ML / Semantic-search.

**Recipe** — markdown spec for a derived dimension at `data/datasets/derived/<name>.recipe.md`. Inputs, output schema, algorithm, refresh cadence, consuming use case.

**Derived table** — Delta table at `data/datasets/derived/<name>/` produced by a batch task.

**Migration** — numbered Python file at `data/migrations/{raw,derived}/<table>/NNN_<name>.py` declaring or evolving a Delta table's schema. `001_initial.py` creates the empty table; later files add columns. Applied by `scripts/apply_delta_migrations.py` on deploy and on local startup. Mirrors Alembic for Postgres but for Delta Lake.

**Wrapping view** — SQL view exposing a derived table to the agent. Indistinguishable from entity/event views downstream.

**Batch task** — async Python at `backend/core/tasks/<name>.py` that produces a derived table. Registered in Procrastinate.

**Toolbox** — purpose-built workspace for a domain (sales, production, service). Determines which views, prompts, tools the agent sees.

**Use case** — a question the agent must answer. Every view column, recipe, and tool exists to serve a use case.

**Notes files** — running logs: `INGEST_NOTES.md` (Phase 1), `ONTOLOGY_NOTES.md` (Phases 2–3), `ONTOLOGY_REVIEW.md` (Phase 4).

## Phases

**Phase 1 — Ingest.** Raw customer files (or system-integration outputs) in, Delta tables and column shortlists out. Skill: `ingest-data`. The skill writes a numbered schema migration per source table *before* any data is ingested — this is what lets staging, production, and every customer fork agree on the table shape, and what makes upstream schema changes (SAP added a column) explicit reviewable diffs instead of silent inference. Human after: read flags, decide what to bounce back to the customer, capture use cases.

**Phase 2 — Build first-pass ontology.** Use cases + raw tables in, entity/event views and a toolbox prompt out. Skill: `build-ontology`. Refuses to run without confirmed use cases. Human after: read views, smoke-test the agent, customer review meeting, decide which derived dimensions to scaffold.

**Phase 3 — Extend with derived dimensions.** Deferred-dimensions list in, recipes + task stubs + derived-table directories + wrapping views (or semantic-search tools) out. Skill: `extend-ontology`. Stops at scaffolding — engineer fills in algorithms, embedding models, vector backend wiring. Human after: implement each recipe, validate, then update prompts to reference the now-populated dimensions.

Derived tables follow the same migration model as raw tables — `extend-ontology` writes a numbered file under `data/migrations/derived/<name>/`, and `scripts/apply_delta_migrations.py` (run by `entrypoint.sh` and `start.sh` after `alembic upgrade head`) creates the empty Delta table. The motivation differs slightly: raw migrations let upstream schemas evolve as explicit code; derived migrations let wrapping views compile against a declared schema *before* the producing task is implemented or has ever run. SQL views are still the exception — they have no on-disk schema independent of their `SELECT`, so editing the `.sql` file *is* the migration.

**Phase 4 — Review.** Whole ontology in, severity-ranked findings out. Skill: `review-ontology`. Read-only — proposes fixes, doesn't apply them. Human after: triage, loop back to the skill that needs to fix the finding, re-review.

Severities: **Blocker** (ontology broken), **Coherence** (artifacts disagree), **Convention** (violates `view-conventions.md` but agent works), **Suggestion**.

## When to skip phases

- Skip `ingest-data` if no fresh data drop arrived
- Re-run `build-ontology` only on new sources or major reshapes; small view fixes are direct edits
- Re-run `extend-ontology` only to scaffold genuinely new dimensions; recipe tweaks and status updates are direct edits
- Re-run `review-ontology` after any material change, before demos, or when the agent acts off

Skipping the human review steps between phases is the most common failure mode.

## File layout

```
docs/
  ontology.md              # rulebook
  ontology-pipeline.md     # this document
  INGEST_NOTES.md          # ingest-data
  ONTOLOGY_NOTES.md        # build-ontology, appended by extend-ontology
  ONTOLOGY_REVIEW.md       # review-ontology

data/datasets/
  <RAW_TABLE>/             # ingest-data (created by migration, populated by ingest)
  <RAW_TABLE>_columns.csv  # ingest-data
  derived/                 # extend-ontology
    <name>/                # derived Delta table (created by migration, populated by task)
    <name>.recipe.md
  views/
    <entity>.sql           # build-ontology
    <derived>.sql          # extend-ontology (wrapping views)

data/migrations/
  raw/
    <RAW_TABLE>/001_initial.py   # ingest-data
  derived/
    <name>/001_initial.py        # extend-ontology

backend/
  core/tasks/<name>.py             # extend-ontology
  core/tools/semantic_search_*/    # extend-ontology
  customer/tasks/__init__.py       # extend-ontology
  customer/tools/__init__.py       # extend-ontology
  customer/queries.py              # build-ontology
  prompts/{toolbox}.md             # build-ontology, then engineers after extend-ontology
```

## What automation cannot do

The skills handle the mechanical work. These remain human:

- **Use case capture** — skills refuse to proceed without confirmed use cases; they can't derive them from data.
- **Algorithm choice** — Precomputed-ML and Semantic-search recipes flag algorithm and embedding model as `placeholder — engineer chooses`.
- **Quality validation** — whether a clustering or semantic search produces *useful* results is an engineer + customer call.
- **Prompt voice** — skills wire entities into prompts; persona and examples want a human.
- **Scope decisions** — "include archived customers?" "service contracts as entities or pre-joined?" These shape the ontology and need a human in the loop.
