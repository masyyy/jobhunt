# Review checklist

Walk these axes in order. For each check, produce findings in the format the main SKILL.md describes.

## Axis 1 — Use-case fit

The central question: does every view and every column earn its place against the stated use cases?

For each **view**:
- Does at least one use case need this entity? If not, why does it exist?
- Is the grain right for the use cases it supports? (Per-customer when the use case is per-order is a mismatch.)
- Are there use cases that *should* be supported by a view but aren't? Note the gap.

For each **column** in each view:
- Which use case references or needs this column?
- If none, is it load-bearing for something structural (a join key, a scope filter)?
- If neither — it's a candidate for removal. **Coherence** finding.

A column being "interesting" or "there in the raw data" is not a reason to expose it. The agent's context is a finite resource; every column it sees is a column it might latch onto.

## Axis 2 — Prompt ↔ view alignment

Open each prompt in `backend/prompts/` alongside the views it describes. Walk every concrete reference.

- **View names**: every view name the prompt mentions must exist as `data/datasets/views/<name>.sql`.
- **Column names**: every column the prompt promises must exist in the corresponding view. Check the SELECT list, not just the raw source.
- **Pre-applied filters**: if the prompt says "data is prefiltered to X", the view must actually apply filter X. A prompt claim without a view enforcement is a **Coherence** finding.
- **Value vocabularies**: if the prompt lists status values (`'open'`, `'completed'`, `'on_hold'`), the view must emit exactly those values, spelled and cased the same way.
- **Described joins**: if the prompt says "join customers to cases via account_id", the column and direction must match.

Common mismatch sources:
- A column was renamed or dropped in the view but the prompt wasn't updated
- A scope gate was added to views but the prompt doesn't advertise it, so the agent tries to broaden queries
- A status code was decoded in the view but the prompt still references the raw code

## Axis 3 — Top-comment quality

The top `-- ...` block of each view is injected into the agent's system prompt. The parser reads consecutive comment lines at the top. Treat everything in that block as LLM-facing.

Required content:
- [ ] **Grain first**: starts with `-- description: One row per <grain>.`
- [ ] **Use case**: one sentence on what decisions this supports
- [ ] **Joins**: explicit FK → target-view mapping for every foreign key
- [ ] **Pre-applied filters**: any scope gate, time window, active-only filter — stated clearly so the agent doesn't re-apply them

Forbidden content (flag as **Coherence** if present):
- Meta-references to ingestion or Delta Lake (`"loaded from _raw_..."`, `"ingested via..."`)
- References to internal tooling (`check_views.py`, `warehouse_debug.py`, `ONTOLOGY_NOTES.md`)
- Historical notes ("we used to have X", "previously Y")
- TODO/FIXME/placeholder markers
- Explanations aimed at Fulcrum engineers rather than the agent
- Detailed implementation notes better left as inline comments below the top block

A good top-comment reads as if the agent just picked up the view spec for the first time and needed to understand what it's looking at.

## Axis 4 — Meta-information leakage

The single test: **does this text help the agent do its job, or is it a note to a Fulcrum engineer?**

Read each prompt and each view top-comment as if you were the agent — a system whose only goal is to answer the user's business question using the views in front of it. For every sentence, ask: does knowing this change what the agent queries, filters, or recommends?

If yes — keep.
If no — it's leakage. **Coherence** finding.

What leakage typically looks like:

- Internal tooling names (`check_views.py`, `warehouse_debug.py`, `ONTOLOGY_NOTES.md`) — the agent doesn't run those.
- Ingestion/infrastructure details (`_raw_*` tables, Delta Lake, DuckDB, Polars) — the agent queries views, not raw.
- Historical carve-outs ("we previously had X, now Y") — past state doesn't affect present queries.
- `TODO` / `FIXME` / "placeholder" / "not yet implemented" — signals to an engineer to finish something.
- References to the template/fork architecture, upstream repo, Fulcrum operations.
- Conceptual framework names (Palantir, Kimball, ontology theory) — the agent needs guidance, not lineage.
- "As documented in..." pointing to files the agent can't read.

What is **not** leakage, despite looking similar:

- `_raw_*` table names inside a SQL `FROM` clause — necessary for the view to work. Only flag when `_raw_` appears in a *comment* or *prompt body* where the agent would see it as guidance.
- Inline SQL comments *below* the top `-- description:` block — humans-only, parser ignores them, not agent-visible.
- Explanations of business concepts the agent genuinely needs ("field service activity with low spare-part spend often means parts are being sourced elsewhere") — that *does* help the agent reason.

The bar: every agent-visible sentence has to earn its place by improving the agent's query decisions. Neither engineering context nor project history meets that bar.

Scope for this axis:
- Prompts in `backend/prompts/*.md`
- Top-comment blocks in `data/datasets/views/*.sql` (consecutive `-- ...` lines at the top)

## Axis 5 — View conventions

Spot-check each view against `view-conventions.md`. These are mostly **Convention** severity (agent can still function). Batch them in the report — don't write a finding per missing underscore.

- [ ] Filename stem matches view name
- [ ] Uses `CREATE OR REPLACE VIEW`
- [ ] Column names are readable English (no `ACCT_ID`, `ord_tot`)
- [ ] Units in names where applicable (`revenue_usd`, `duration_minutes`, `weight_kg`)
- [ ] Status codes decoded with CASE (no raw `'A'`/`'I'`/`'P'` values)
- [ ] FK names consistent across views (`customer_id` everywhere, not `acct_id` in one place)
- [ ] Boolean columns read as assertions (`is_active`, not `flag_active`)
- [ ] Types explicitly cast (dates, numbers)
- [ ] Join keys are non-NULL (or guarded)
- [ ] Noise filters applied (inactive, test, out-of-scope rows excluded)
- [ ] No source-system bookkeeping columns exposed (audit timestamps, ETL fields, system hashes)

## Axis 6 — Column-level profiling

For each view, run:

```bash
uv run python scripts/warehouse_debug.py profile <view>
```

Read the NULL rates, cardinality, and top values section. Judge each column against the use cases:

| Pattern | Interpretation | Severity |
|---|---|---|
| 100% NULL | Column is dead — remove from view | Coherence |
| >70% NULL, not use-case-backed | Low-signal — justify or remove | Coherence |
| Cardinality = 1 with some NULL | Weak boolean — consider making explicit `is_X` column | Suggestion |
| Cardinality = 1, zero NULL | Constant — remove, zero information | Coherence |
| Near-unique (looks like ID) but no join target | Dangling ID — remove or document | Coherence |
| Low cardinality, raw codes visible | Undecoded enum — add CASE | Convention |
| Numeric column, no unit in name | Implicit unit — rename | Convention |
| Two columns that always agree | Duplicate — remove one | Suggestion |

Do not flood the report. Every finding must be tied to either a use case it fails to serve or a rule from `view-conventions.md`.

## Axis 7 — Named queries + tools

For each entry in `backend/customer/queries.py` `DASHBOARD_QUERIES`:

- Does the SQL reference only views, never `_raw_*` tables? (If it queries raw, that's a **Coherence** finding — dashboards should ride the same semantic layer as the agent.)
- Do the columns the query returns match the frontend interface in `frontend/src/customer/queries.ts`?
- Is the query name descriptive and consistent with the toolbox?

For each toolbox in `backend/customer/tools/__init__.py`:

- Are the tools assigned appropriate to the use cases? A sales toolbox without `execute_sql` is probably wrong.
- If a tool references specific views or columns, do they exist?

## Axis 8 — Structural validators

Run all three and capture their output verbatim if any fail:

```bash
uv run python scripts/check_ontology.py
uv run python scripts/check_views.py
uv run python scripts/check_customer_config.py
```

Failures are **Blockers**. No exceptions — a failing `check_views.py` means a view is broken and the agent can't use it.

Then run the migration runner — it should be a no-op:

```bash
uv run python scripts/apply_delta_migrations.py
```

If it reports any pending migrations or any failures, that's a **Blocker**: deploy didn't run, or the runner is broken.

## Axis 9 — Schema migrations (raw + derived)

Both raw and derived Delta tables live under a migration regime. Migrations declare schemas independently of data; `scripts/apply_delta_migrations.py` materializes empty tables before ingest or task runs.

For each raw Delta table at `data/datasets/<TABLE>/`:

- [ ] **Migration directory exists**: `data/migrations/raw/<TABLE>/` exists with at least `001_initial.py`. Missing = **Blocker** — the table was created via legacy schema-inference and isn't reproducible across environments.
- [ ] **Applied version current**: `DeltaTable(uri).metadata().configuration["fulcrum.migration_version"]` equals the highest numbered migration in the directory. Drift = pending migrations not yet applied = **Blocker**.
- [ ] **Schema in migration matches table**: the columns and primitive types in the latest migration match what `DeltaTable(uri).schema()` reports. Drift = somebody bypassed the migration runner = **Coherence**.
- [ ] **No edits to applied migration files**: `001_initial.py` should not have been edited after first apply. Use git blame to spot-check; suspicious edits are **Coherence**.

For each migration directory at `data/migrations/raw/<TABLE>/` without a corresponding `data/datasets/<TABLE>/`: **Coherence** — declared but never ingested. Either ingest is pending (note in `INGEST_NOTES.md`) or the migration is dead and should be removed.

(Derived-side migration coverage lives in Axis 11 alongside the rest of the derived-dimension checks.)

## Axis 10 — ONTOLOGY_NOTES.md health

If `docs/ONTOLOGY_NOTES.md` exists, check:

- Are there assumptions marked unchecked that should have been resolved by now?
- Are there open questions the data actually answers (so they can be closed)?
- Are there scope decisions in the notes that aren't reflected in the views?
- Are there views/columns not mentioned in the entity summary?

If the file is missing entirely and use cases are non-trivial, flag as **Coherence**: the customer review cycle depends on this artifact.

## Axis 11 — Derived dimensions

If `data/datasets/derived/` exists, the customer has scaffolded derived dimensions via `extend-ontology`. Check coherence between the four artifacts each dimension produces:

For each `data/datasets/derived/<name>.recipe.md`:

- [ ] **Recipe inputs are real**: every view named under `## Inputs` exists in `data/datasets/views/` and exposes every column the recipe references
- [ ] **Output schema matches consumer view**: the wrapping view (or join) selects only columns the recipe declares it outputs
- [ ] **Migration directory exists**: `data/migrations/derived/<name>/` exists with at least `001_initial.py`. Missing = **Coherence**.
- [ ] **Schema doc matches migration**: the recipe's `## Output schema` section describes the same columns and types as the latest migration's resulting Delta schema. Drift = **Coherence**.
- [ ] **Applied version current**: `DeltaTable(uri).metadata().configuration["fulcrum.migration_version"]` equals the highest numbered migration in the directory. Pending unapplied migrations = **Blocker** (deploy hasn't run, or runner failed).
- [ ] **Task is registered**: the function name in `**Task:**` exists in `backend/core/tasks/`, is registered in `backend/infrastructure/tasks/tasks.py`, and is wired into `backend/customer/tasks/__init__.py`
- [ ] **Use case still applies**: the use case named under `## Consumed by` is in the current prompt or `ONTOLOGY_NOTES.md`. A recipe orphaned from its use case is a **Coherence** finding.
- [ ] **Status reflects reality**: if the status checklist claims `First run produced data`, the derived table directory should be non-empty (more than just `_delta_log/`)

For each derived directory `data/datasets/derived/<name>/` without a recipe: **Coherence** finding (untracked artifact).

For each task referencing a recipe whose status says `Algorithm implemented` but the body still raises `NotImplementedError`: **Blocker**.

For semantic-search recipes specifically:

- [ ] **Tool is registered**: the tool named in `**Tool:**` exists in `backend/core/tools/` and is in `TOOLBOX_TOOLS` for at least one toolbox
- [ ] **No SQL view exists** for the corpus — semantic search returns IDs the agent joins back, not a queryable view

For dimensions whose status says they're populated but the wrapping view returns 0 rows in `check_views.py` output: **Coherence** (status drift).

If `data/datasets/derived/` does not exist, no findings on this axis. Note in the report under "What was not reviewed" that no derived dimensions are scaffolded.

## Axis 12 — Overall shape

Zoom out. Answer:

- Are there too many views? (Rule of thumb: one per business entity. If a view exists only to be joined into one other view, consider merging.)
- Are there too few views? (If a prompt repeatedly asks the agent to construct the same multi-join, pre-join it.)
- Is the grain consistent across related views? (A `customers` view with one row per customer and a `customer_snapshots` view with one row per customer per month is fine; two views with overlapping but different grains is confusing.)
- **Do any views overlap unnecessarily?** Spot-check: if two views share the same grain and a large fraction of columns, one of them is probably redundant or the pair is a missed chance to consolidate. Not a strict metric — just an eye check while you're already reading the views.
- Does anything in the ontology feel like it's there for the data's convenience rather than the user's decisions?

These are **Suggestion**-level unless they clearly block a use case.
