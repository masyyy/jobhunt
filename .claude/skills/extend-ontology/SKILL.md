---
name: extend-ontology
description: Identify and scaffold derived dimensions a customer ontology needs beyond raw entity views — peer groups, expected baselines, scoring, co-purchase associations, semantic search over unstructured text. Reads use cases against existing views, classifies each missing dimension by how it's produced (SQL-now / precomputed-deterministic / precomputed-ML / semantic-search), and scaffolds recipes, batch tasks, derived tables, and tools. Stops at scaffolding — engineers implement the actual algorithms. Runs after build-ontology, before review-ontology.
allowed-tools: Bash Read Write Edit Grep Glob
---

# Extend ontology

The first-pass ontology (from `build-ontology`) is direct projections of raw data: rename, decode, join, filter. Real use cases often need more — comparisons against expected behavior, similarity to other entities, retrieval over unstructured text. This skill identifies those gaps and scaffolds the infrastructure to fill them.

This skill **does not implement ML or write embeddings code.** It produces:

- A recipe describing what to compute
- A registered batch task with the right input/output signature
- A derived Delta table the task will write to
- A view wrapping the derived table for the agent
- For semantic search: a tool registration the agent can call

The actual algorithm (clustering, scoring, embedding choice, prompt engineering) is an engineer's job. The scaffolding is consistent across customers; the domain expertise lives in the task implementations.

## Prerequisites

Both must be true before this skill runs:

- `build-ontology` has produced entity and event views in `data/datasets/views/*.sql`
- The use cases are documented (in `backend/prompts/{toolbox}.md`, `docs/ONTOLOGY_NOTES.md`, or stated by the user)

If either is missing, STOP. Tell the user to run `build-ontology` first or to provide use cases.

**The handoff from `build-ontology`:** that skill writes a `## Derived dimensions deferred to extend-ontology` section in `docs/ONTOLOGY_NOTES.md` listing dimensions it noticed but couldn't model with views alone. **Read that section first** — it's the explicit breadcrumb the prior phase left for you. Use cases can also identify dimensions that section misses; treat it as a starting point, not an exhaustive list.

## When NOT to use this skill

For small targeted changes, edit the relevant file directly — don't invoke this skill:

- Tweaking the algorithm in one task body
- Editing one recipe's open-questions section
- Renaming a column in one wrapping view
- Updating one recipe's status checklist after the engineer finishes implementation

Use this skill when scaffolding a *new* derived dimension end-to-end, or batch-scaffolding several at once.

## Orient before acting

Check what's already scaffolded so you don't clobber existing recipes or duplicate tasks.

```bash
ls data/datasets/derived/*.recipe.md 2>/dev/null
ls data/datasets/derived/ 2>/dev/null
ls backend/core/tasks/ 2>/dev/null
```

Three cases:

- **Cold start** (no `derived/` directory, no derived tasks): proceed with the full procedure.
- **Extending an existing scaffold** (some recipes already exist): read every existing recipe's `## Status` section first. State to the user: "I see <N> recipes already scaffolded: <list with status>. I'll add <M> new ones for <gaps>, leaving the existing ones alone unless you flag otherwise."
- **Re-scaffolding a recipe that exists**: targeted fix — edit the recipe directly, don't re-run the skill. If the engineer needs to change the algorithm, they edit the task body and bump the recipe's `## Status` checkboxes.

Never `cp` over an existing recipe file. The skill's per-dimension steps below now check for existence before scaffolding.

## Deliverables

Per derived dimension identified:

1. **Recipe markdown** at `data/datasets/derived/<name>.recipe.md` — describes inputs, output schema, algorithm or method, refresh cadence, consuming use case
2. **Batch task stub** at `backend/core/tasks/<name>.py` — async function with the input/output signature implied by the recipe; body raises `NotImplementedError` with a pointer to the recipe
3. **Task registration** in `backend/infrastructure/tasks/tasks.py` and `backend/customer/tasks/__init__.py` — wired into the existing task infrastructure
4. **Initial Delta migration** at `data/migrations/derived/<name>/001_initial.py` — declares the Delta schema and creates the empty table when `scripts/apply_delta_migrations.py` runs
5. **Wrapping view** at `data/datasets/views/<name>.sql` — exposes the derived table to the agent (or joins it back into an existing entity view); compiles immediately because step 4 materialized the empty table

For semantic-search dimensions only:

6. **Tool registration** at `backend/core/tools/<tool_name>/tool.py` — semantic search function calling whatever vector backend the project uses; added to the relevant toolbox in `backend/customer/tools/__init__.py`

Out of scope:
- Implementing the actual algorithm in the task body (engineer's job)
- Choosing model hyperparameters, embedding models, or distance metrics (engineer's job, captured in recipe as a placeholder)
- Running the batch jobs (orchestration; engineer schedules)
- Coherence audit — that's `review-ontology`

## The four classes of derived dimension

Every missing dimension falls into one of four buckets. The skill's job is to classify each one before scaffolding.

| Class | Meaning | Output shape |
|---|---|---|
| **SQL-now** | Computable at query time with window functions / aggregations on existing views | A view, no derived table, no task |
| **Precomputed-deterministic** | Fully deterministic but too expensive or complex for query time (e.g. co-purchase matrix, customer-similarity by feature vector with a fixed formula) | Recipe + task + derived table + view |
| **Precomputed-ML** | Needs a model — clustering, scoring, classification, regression | Recipe + task + derived table + view; task body is a stub |
| **Semantic-search** | Retrieval over unstructured text by meaning | Recipe + indexing task + derived index (vector store) + tool registration; no SQL view (the tool returns IDs the agent joins back) |

Classification is a judgment call. Heuristics:

- "How often does the agent need this?" If every query needs it, precompute. If rare, SQL-now is fine even if slower.
- "Is the formula fixed?" If yes (e.g. "median of cohort"), deterministic. If you'd train and tune, ML.
- "Is the input text or numeric?" Text retrieval = semantic-search. Numeric similarity over fixed features = ML clustering.
- "Will the engineer implement this in a week?" If yes, scaffold it. If "we should explore whether…", defer with a note rather than scaffolding speculatively.

When unsure between deterministic and ML, prefer **deterministic with a note in the recipe** that ML may replace it later. Cohort medians beat clusters as a v1; clusters beat medians as a v2. Don't scaffold ML before deterministic has been tried.

## Procedure

### 1. Read the use cases against the existing views

Cold-start: the user will have invoked this skill because they suspect the ontology is missing something. Confirm what.

```bash
cat backend/prompts/*.md docs/ONTOLOGY_NOTES.md 2>/dev/null
ls data/datasets/views/*.sql
```

For each documented use case, ask: **what does the agent need that the current views don't expose?** Walk the list. For each answer, write a one-line statement:

```
UC1 (Proactive Installed Base Monetization) needs:
  - expected annual spend per machine — comparison against actual baseline
  - peer group identity per customer — to compute the expected baseline
  - co-purchase associations — for "parts typically bought together"
```

Present this list to the user before scaffolding anything:

> "Reading <UC sources> against the existing views, I think these dimensions are missing: <list>. Does this match your understanding? Anything to add or remove?"

Wait for confirmation. The cost of scaffolding the wrong dimension is a stub task that no one ever fills in — clutter that has to be cleaned up later.

### 2. Classify each dimension

For each confirmed dimension, classify it into one of the four buckets. Write the classification next to each item:

```
- expected annual spend per machine — SQL-now (cohort median via window functions)
- peer group identity per customer — Precomputed-ML (clustering on feature vector)
- co-purchase associations — Precomputed-deterministic (basket-pair counts)
- find similar past cases by description — Semantic-search (case text corpus)
```

If a dimension is **SQL-now**, treat it like a `build-ontology` view and add it directly. The recipe machinery is overhead for those — write the SQL, validate, done. Do not produce a recipe file for SQL-now dimensions.

For the other three classes, proceed to scaffolding.

### 3. Scaffold each non-SQL-now dimension

For each one, first check whether it's already scaffolded:

```bash
test -f data/datasets/derived/<name>.recipe.md && echo "recipe exists — skip"
test -f backend/core/tasks/<name>.py && echo "task exists — skip"
```

If any artifact exists for this dimension, **skip the dimension entirely** and tell the user it was already scaffolded. Targeted edits are not this skill's job.

For each genuinely new dimension:

**a) Write the recipe.** Copy the template (only if the recipe doesn't exist):

```bash
cp .claude/skills/extend-ontology/recipe-template.md data/datasets/derived/<name>.recipe.md
```

Fill in the template fields. The recipe is the spec the engineer implements against. It should be concrete enough that an engineer can read it and start coding without re-deriving the use case from scratch.

For **Precomputed-ML** recipes: name a *starting* algorithm (e.g. "k-means on standardized features, k chosen by silhouette") but flag it as `placeholder — engineer chooses` in the algorithm section. Don't pretend you've designed the model.

For **Semantic-search** recipes: name a *placeholder* embedding model (e.g. `text-embedding-3-small`) and flag it the same way. The engineer picks based on cost/quality tradeoffs the skill can't make.

**b) Declare the Delta schema as a migration.** The Delta table itself is created by a migration runner, not by the task. This guarantees the wrapping view (or parent-entity LEFT JOIN) compiles immediately, before the task is implemented.

```bash
mkdir -p data/migrations/derived/<name>
cp .claude/skills/extend-ontology/migration-template.py \
   data/migrations/derived/<name>/001_initial.py
```

Edit `001_initial.py`: replace the placeholder `SCHEMA` with the columns from the recipe's `## Output schema` section, using `deltalake.schema.PrimitiveType` types (`string`, `integer`, `long`, `float`, `double`, `boolean`, `timestamp`, `date`, `decimal(p,s)`, etc.). Mark required columns with `nullable=False`.

Then apply migrations to materialize the empty Delta table:

```bash
uv run python scripts/apply_delta_migrations.py
```

This creates `data/datasets/derived/<name>/_delta_log/` with the declared schema and zero data files. The wrapping view (next step) will compile against it immediately and return zero rows until the task fills the table.

**Schema evolution later:** when the recipe gains a column, write a new numbered migration (`002_add_<column>.py`) using `dt.alter.add_columns([...])` rather than editing `001_initial.py`. The runner stamps the applied version on the Delta table itself, so re-runs are idempotent.

**c) Stub the batch task.** Create `backend/core/tasks/<name>.py`:

```python
async def <name>(deps: TaskDeps) -> None:
    """<one-line summary from recipe>.

    See data/datasets/derived/<name>.recipe.md for inputs, output schema,
    and algorithm. This stub must be implemented before the wrapping view
    returns useful rows.
    """
    raise NotImplementedError(
        "Implement per data/datasets/derived/<name>.recipe.md"
    )
```

Register it in `backend/infrastructure/tasks/tasks.py` and `backend/customer/tasks/__init__.py` following the existing task patterns — read a sibling task in `backend/core/tasks/` to copy the registration shape. If the task needs a `queueing_lock` (refresh shouldn't run concurrently with itself), include it.

**d) Write the wrapping view.** For Precomputed-deterministic and Precomputed-ML:

```sql
-- description: One row per <grain>. <Use case the dimension serves>.
-- Joins: <key> -> <existing_entity_view>.<key>.
CREATE OR REPLACE VIEW <name> AS
SELECT
    *
FROM read_delta('data/datasets/derived/<name>')
```

Or join back into the entity view it extends — see `view-conventions.md` (in `build-ontology`) for the join pattern.

**e) For Semantic-search only: scaffold the tool.** Create `backend/core/tools/semantic_search_<corpus>/tool.py`:

```python
def semantic_search_<corpus>(
    ctx: RunContext[AgentDeps], query: str, k: int = 10
) -> list[dict]:
    """Return up to k <corpus> entries most similar to query.

    See data/datasets/derived/search_<corpus>.recipe.md for indexing.
    Implementation pending — wire to vector backend.
    """
    raise NotImplementedError(
        "Implement per data/datasets/derived/search_<corpus>.recipe.md"
    )
```

Add to the relevant toolbox(es) in `backend/customer/tools/__init__.py` `TOOLBOX_TOOLS`.

Do not write a SQL view for semantic-search dimensions — the tool is the agent's interface, not a view. The tool returns entity IDs the agent then queries via existing views.

### 4. Validate

```bash
uv run python scripts/apply_delta_migrations.py  # Delta tables exist with declared schemas
uv run python scripts/check_ontology.py          # views still conform
uv run python scripts/check_views.py             # views compile (derived tables empty is OK; views just return zero rows)
uv run python scripts/check_customer_config.py   # FE/BE registries in sync
```

A wrapping view over an empty derived table compiles and returns zero rows. That's expected — `check_views.py` reports it but doesn't fail. Note in `ONTOLOGY_NOTES.md` which derived tables are awaiting their first task run.

### 5. Update ONTOLOGY_NOTES.md

If a `## Derived dimensions scaffolded` section already exists in `ONTOLOGY_NOTES.md`, **append rows** to its table — do not rewrite the section. Existing rows reflect prior scaffolding the engineer may already be working on; their status is the source of truth.

If no such section exists, append it:

```markdown
## Derived dimensions scaffolded

| Dimension | Class | Recipe | Task | Status |
|---|---|---|---|---|
| customer_peer_groups | Precomputed-ML | data/datasets/derived/customer_peer_groups.recipe.md | refresh_customer_peer_groups | Stub — engineer to implement |
| co_purchase_pairs | Precomputed-deterministic | data/datasets/derived/co_purchase_pairs.recipe.md | refresh_co_purchase_pairs | Stub — engineer to implement |
| search_cases | Semantic-search | data/datasets/derived/search_cases.recipe.md | index_cases | Stub — engineer to implement |
```

This section is the handoff to the engineer who fills in the algorithms.

### 6. Do NOT update prompts yet

Until the tasks have run and the derived tables have data, the wrapping views return empty results. Mentioning them in the prompt now would have the agent reaching for empty entities. Leave the prompts referencing only the first-pass views until the engineer confirms the derived tables are populated, then a follow-up prompt update can mention them.

Note this in `ONTOLOGY_NOTES.md` so the engineer remembers to update prompts after their implementations land.

## What good looks like

- Each scaffolded dimension has a recipe an engineer can read in one sitting and start implementing
- Task stubs raise `NotImplementedError` clearly, with pointers to the recipe
- Wrapping views compile and reference the derived table directory
- `ONTOLOGY_NOTES.md` lists every scaffolded dimension with its current status
- Nothing is scaffolded that the use cases don't actually need

## What to avoid

- Scaffolding speculatively — every stub is a maintenance burden until implemented
- Implementing ML or embedding code yourself — this skill stops at scaffolding
- Writing recipe files for SQL-now dimensions — they don't need them
- Updating prompts to reference dimensions whose tables are empty
- Skipping the user-confirmation step in step 1 — the wrong scaffolding is worse than none
- Choosing embedding models or clustering algorithms in the recipe — flag them as `placeholder — engineer chooses`
