---
name: build-ontology
description: Build the first-pass semantic layer for a customer — entity and event views over already-ingested raw Delta tables. Reads use cases, profiles columns, writes one DuckDB view per business entity, and updates toolbox prompts. Assumes ingest-data has already run. Does not produce derived/clustered/precomputed dimensions — that's extend-ontology.
allowed-tools: Bash Read Write Edit Grep Glob
---

# Build ontology

You are building the semantic layer between a customer's raw data and the Fulcrum agent. The ontology is what the LLM sees and queries — get it right and the agent is grounded; get it wrong and the agent hallucinates.

This skill produces **first-pass entity and event views** directly over raw Delta tables. It does not produce derived dimensions (peer groups, expected baselines, churn scores, semantic search indices) — those are `extend-ontology`'s job and run as a third phase.

Read [docs/ontology.md](../../../docs/ontology.md) first for the conceptual foundation (borrowed from Palantir + Kimball, adapted for LLMs). This skill is the operational playbook for actually doing it.

## Prerequisite

`ingest-data` must have run. This skill expects:

- Raw Delta tables under `data/datasets/<TABLE>/`
- Column-usage CSVs at `data/datasets/<TABLE>_columns.csv`
- A populated `docs/INGEST_NOTES.md` describing what was ingested

If those don't exist, STOP and tell the user to run `ingest-data` first. Do not ingest opportunistically inside this skill.

## When NOT to use this skill

For small targeted changes, edit the relevant file directly — don't invoke this skill:

- Renaming one column in one view
- Fixing a CASE expression
- Adding one missing JOIN in an existing view
- Tweaking a single sentence in a toolbox prompt

Use this skill when the work is structural: a new entity to model, a major reshape, or a fresh customer onboarding.

## Orient before acting

Check what already exists so you know whether to cold-start or extend.

```bash
ls data/datasets/views/*.sql 2>/dev/null
test -f docs/ONTOLOGY_NOTES.md && echo "notes exist"
cat backend/prompts/*.md 2>/dev/null | head -50
```

Three cases:

- **Cold start** (no views, no notes): proceed with the full procedure below.
- **Extending an existing ontology** (views and/or notes present): read every existing view's top comment and `ONTOLOGY_NOTES.md` first. State up front to the user: "I see <N> existing views: <list>. I'll add <M> new ones for <use cases>, leaving the existing ones alone unless you tell me otherwise." Treat this run as additive.
- **Reshaping an existing view**: this is a targeted fix — edit the view directly, don't re-run the skill.

Never `cp` over an existing `ONTOLOGY_NOTES.md` (step 0 below has the safe pattern).

## Deliverables

Every invocation produces:

1. **SQL views** under `data/datasets/views/*.sql` — one per business entity, agent-facing
2. **Prompt updates** to `backend/prompts/{toolbox}.md` — referencing the new entities by their business names
3. **`docs/ONTOLOGY_NOTES.md`** — assumptions made, open questions for the customer, data-quality observations specific to ontology decisions (NOT raw-data observations — those live in `INGEST_NOTES.md`)

Out of scope:
- Ingesting raw data — `ingest-data`
- Defining derived/clustered/computed dimensions — `extend-ontology`
- Coherence audit across the finished ontology — `review-ontology`

## Use cases first (STOP condition)

Before writing any view, confirm the use cases. The ontology's shape is decided by what the agent is for — without use cases, you're reshaping data for its own sake.

Look for use cases in:
1. A briefing from the user in the current conversation
2. Existing `backend/prompts/{toolbox}.md` (if onboarding into an existing toolbox)
3. `docs/ONTOLOGY_NOTES.md` if it predates this run
4. `docs/INGEST_NOTES.md` may contain hints from the data drop conversation
5. Customer-supplied materials the user has referenced

If use cases are **clear** — the user has stated them, or they're obvious from existing artifacts — write them down as a short list and proceed. Reference this list when deciding which entities to model and which columns to keep.

If use cases are **NOT clear**, STOP and ask the user:

> "Before I start building the ontology, I need to know what decisions the agent is meant to support. Can you list the top 3-5 user questions or workflows the agent will handle? Examples: 'find customers whose spend has dropped', 'surface stalled quotes', 'recommend parts similar customers bought'. Without this I'd be guessing at which entities and columns matter."

Do not build views for "everything that looks interesting in the data" — that produces a bloated ontology the agent cannot navigate.

## The two phases

### Phase 1 — Explore

Understand what each raw table contains, which columns carry signal, and how tables relate. The goal is to find **entities worth modeling** and **columns worth exposing**, not to write a data dictionary.

**Step 0 — Start (or continue) the notes file before you explore.**

The notes file is not a write-up at the end — it's a running log that shapes the customer review meeting.

If `docs/ONTOLOGY_NOTES.md` does not exist, copy the template:

```bash
cp .claude/skills/build-ontology/ontology-notes-template.md docs/ONTOLOGY_NOTES.md
```

If it already exists, **do not overwrite it**. Read it end-to-end so you know what assumptions and scope decisions were already made, then append new entries as you go. Prior open questions might already be answered by this round of exploration — close them out rather than re-discovering them.

Every CASE expression you decide on, every filter you apply, every type guess, every cryptic column you couldn't decode — write it down as you go. Empty notes at the end of exploration almost always means assumptions were silently baked into the views.

**Step 1 — Read what ingest produced.**

```bash
cat docs/INGEST_NOTES.md
ls data/datasets/*_columns.csv
```

The column CSVs are your shortlist. They've already been pruned of constants and all-NULL columns by `generate_column_usage.py`. You still have to judge which of the remaining columns matter for the use cases.

**Step 2 — Profile the surviving columns.**

For each table that looks like a real entity (not a junction/noise table):

```bash
uv run python scripts/warehouse_debug.py profile _raw_<TABLE> --sample 20
```

Read: sample rows, NULL rates, distinct counts, top values. Look for:
- **Codes needing decode**: a text column with a small number of distinct short values (`A`, `B`, `X` or `COMP`, `WIP`) — these are status/type codes that must become CASE expressions
- **Dangling IDs**: an ID column whose values don't resolve to any other table's PK — usually safe to drop from agent view
- **Units-in-the-name gaps**: a `duration` column in seconds vs. minutes vs. hours — the LLM will guess wrong; the view must rename to `duration_minutes`
- **Free-text dumps**: long-form columns rarely useful to the agent unless you extract something (e.g. SAP IDs embedded in case text)

**Step 3 — Verify keys and relationships.**

For every suspected primary key:

```bash
uv run python scripts/warehouse_debug.py query "SELECT COUNT(*), COUNT(DISTINCT <PK>) FROM _raw_<TABLE>"
```

For every suspected foreign key, check how well it resolves:

```bash
uv run python scripts/warehouse_debug.py query \
  "SELECT COUNT(*) AS orphans FROM _raw_A a LEFT JOIN _raw_B b ON a.<FK> = b.<PK> WHERE b.<PK> IS NULL"
```

A high orphan rate means either (a) the FK is wrong, (b) the matching table wasn't ingested, or (c) the data crosses a scope the customer didn't mention. Record the finding in `ONTOLOGY_NOTES.md`.

**Step 4 — Escalate unclear columns to the oracle.**

When profiling leaves you uncertain about what a column *means* (not just what's in it), use the column oracle — it asks an LLM behind a chinese wall without exposing raw values to you:

```bash
uv run python scripts/column_oracle.py <TABLE> "Column A" "Column B" \
    -q "Is this an amount, a quantity, or a count? What unit?"

# Or batch-profile all useful columns:
uv run python scripts/column_oracle.py <TABLE> --profile
```

Good use cases: ambiguous amount columns, SAP-style code columns with no reference table, fields whose name is cryptic. Log every oracle answer back into `ONTOLOGY_NOTES.md` as an assumption — the LLM is guessing too.

See [exploration-playbook.md](exploration-playbook.md) for the full set of probe queries, plus the heuristics that decide whether a column is worth keeping in a view.

### Phase 2 — Build views

Once you know which entities exist and which columns matter, write one view per business entity.

**The top comment is the agent's entire description of the view.** Format:

```sql
-- description: One row per <grain>. <What this view is for, and when to use it>.
-- Use this for <decisions>. Joins: <PK> -> <other_view>.<FK>.
```

The parser consumes all consecutive `-- ...` lines at the top as the description (verified by `tests/test_duckdb_views.py`). Use the lines you need, then switch to non-comment SQL.

**Follow the conventions in [view-conventions.md](view-conventions.md).** The short version:

- Use `CREATE OR REPLACE VIEW <name> AS SELECT ...`
- **The filename stem must match the view name** — `customers.sql` ↔ `VIEW customers`
- Rename every source column to readable English (`ACCT_ID` → `customer_id`)
- Decode all status codes with CASE expressions (`status = 'Delivered'`, not `STAT_CD = 'D'`)
- Denormalize via JOINs — the agent should never need to join for name resolution
- Include units in names: `revenue_usd`, `duration_minutes`, `weight_kg`
- Pre-compute simple derived metrics: `scrap_rate_pct`, `days_since_last_activity`, `is_churned` (only if computable from columns *in this view*; cross-entity derivations belong in `extend-ontology`)
- Boolean columns read as assertions: `is_active`, `has_open_quotes`
- Filter noise (inactive records, test accounts, out-of-scope rows) in the view
- Drop columns with no ontological purpose — every visible column is a potential distraction
- Use the same FK name across all views (`customer_id` everywhere)
- No NULLs in join keys — guard with `WHERE` or `COALESCE`

**What goes here vs. in `extend-ontology`:**

This skill produces views that are **direct projections of raw tables** — rename, decode, join, filter, simple per-row computation. If a column requires:
- Aggregation across customers (e.g. peer-group medians)
- Output of a batch job (clustering, embedding, scoring)
- Time-series modeling (trend extrapolation, churn probability)
- Vector / semantic search

…it does not belong in this phase. Make a note in `ONTOLOGY_NOTES.md` under `## Derived dimensions deferred to extend-ontology` listing the dimension and the use case it serves. `extend-ontology` will pick those up.

**Inline comments are for humans, not the agent.** The top `-- description:` block reaches the LLM. Anything after the first non-comment line is invisible to the LLM but still useful for developers. Document tricky CASE rationale, date-window decisions, or scope-gate logic inline even though the agent won't read it.

**Validate each new view as you write:**

```bash
uv run python scripts/check_ontology.py data/datasets/views/<new>.sql
uv run python scripts/check_views.py
```

`check_ontology.py` enforces: description on first non-whitespace line, uses `CREATE OR REPLACE VIEW`, view name matches filename. `check_views.py` actually compiles every view against the raw tables and counts rows.

**If `check_views.py` has a load order**, update it. The script ingests views in a fixed order; views that reference other views need to come after their dependencies. Put any scope-gate view (one that serves as an `IN (SELECT ...)` filter for others) first.

### Update prompts

After the views exist, make the toolbox prompt aware of them.

If `backend/prompts/{toolbox}.md` already exists, read it first and edit additively — preserve persona, examples, and existing guidance unless they contradict the new views. Only fully rewrite a prompt if its premise (the toolbox's purpose) has changed.

For each toolbox that will use the new entities, edit `backend/prompts/{toolbox}.md`:

- Describe the domain in business terms the user cares about, not view names
- State any pre-applied filters (sales-org scope, time window) so the agent doesn't try to "broaden" by querying raw tables
- Call out multi-currency or multi-unit situations
- List common questions users will ask and the views/columns that answer them
- Document limitations honestly (e.g. "customer-level spend only, not machine-level")

The agent sees the prompt + the auto-generated schema section (views + columns + descriptions). The prompt must be consistent with the views — if a view drops a column, the prompt must not reference it.

If you noted derived dimensions deferred to `extend-ontology`, do **not** mention them in the prompt yet. The prompt should only reference what the views currently expose.

### Register queries and toolbox wiring

If the customer needs dashboard views (not just chat), add named queries:

1. Add a member to `backend/customer/queries.py` `DashboardQuery` + a SQL string in `DASHBOARD_QUERIES`
2. Add the matching member to `frontend/src/customer/queries.ts` `DashboardQuery`
3. Add row-shape TypeScript interfaces for the return columns

If the customer needs new tools or tasks, wire them in `backend/customer/tools/__init__.py` and `backend/customer/tasks/__init__.py`.

### Validate the deliverable

Before handing off:

```bash
uv run python scripts/check_ontology.py           # every view file conforms
uv run python scripts/check_views.py              # every view compiles + returns rows
uv run python scripts/check_customer_config.py    # FE/BE registries in sync
```

All three must pass. `ONTOLOGY_NOTES.md` must list every assumption as an unchecked box (the customer confirms them later) and every open question you couldn't resolve from the data alone.

Tell the user that if any use cases need **derived dimensions** (peer groups, expected baselines, scoring, semantic search), the next step is `extend-ontology`. Otherwise, the ontology is ready for `review-ontology`.

## What good looks like

- An agent answering real customer questions with view-derived facts, not hallucinations
- Zero raw `_raw_*` tables exposed to the agent (views cover everything relevant)
- Every column name is readable English with units
- Every status code is decoded
- `ONTOLOGY_NOTES.md` is honest about what you guessed, and lists derived dimensions deferred to `extend-ontology`

## What to avoid

- Re-ingesting raw data inside this skill — `ingest-data` owns that phase
- Writing a view per raw table — one view per business *entity*, often joining multiple raw tables
- Pre-computing dimensions that need batch jobs or ML — defer to `extend-ontology`
- Exposing audit timestamps, ETL bookkeeping columns, system hashes — all noise to the agent
- Skipping `ONTOLOGY_NOTES.md` — the customer review meeting depends on it
- Running `check_views.py` with a new scope gate missing from the load order — silent failure of downstream views
- Guessing at meanings of cryptic columns instead of asking the oracle or the customer
