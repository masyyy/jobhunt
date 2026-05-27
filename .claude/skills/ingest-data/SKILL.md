---
name: ingest-data
description: Ingest a customer's raw CSV/TSV/Excel exports into Fulcrum as Delta Lake tables, prune obviously-useless columns, and produce an initial column-usage report. First phase of customer onboarding — runs before build-ontology. Use when the customer ships a fresh data drop or when adding new source systems to an existing fork.
allowed-tools: Bash Read Write Edit Grep Glob
---

# Ingest data

You are getting a customer's raw files into the warehouse so the rest of the ontology pipeline can read them. This skill stops at "raw tables exist + we know which columns are worth looking at." It does not design entities, write views, or update prompts — that's `build-ontology`.

## Deliverables

Every invocation produces:

1. **Raw-table schema migrations** at `data/migrations/raw/<TABLE>/001_initial.py` — declares the Delta schema for each new source table; applied by `scripts/apply_delta_migrations.py` to create the empty Delta table before any data lands
2. **Raw Delta Lake tables** under `data/datasets/<TABLE>/` — populated by ingestion appending against the migrated schema (no longer "infer schema from the file"; mismatches are explicit errors)
3. **Column-usage CSVs** at `data/datasets/<TABLE>_columns.csv` — pruned shortlist of columns with signal
4. **Schema dump** captured from `warehouse_debug.py schema` — list of every raw table and its column count
5. **`docs/INGEST_NOTES.md`** — what was received, what was skipped and why, any data-quality observations the customer should know about

Out of scope: deciding which entities to model, writing views, profiling distributions per column, asking the column oracle. Those are `build-ontology`.

The migration-first model matters because production data flows from upstream system integrations (SAP, Salesforce, customer APIs) over time, not as a single CSV drop. The migration files commit the schema to git so every environment — local, staging, production, every customer fork — sees the same table shape, and so upstream schema changes are explicit code reviewable diffs rather than silent inference at ingest time. See `docs/ontology-pipeline.md` for the full picture.

## When to use

- A customer just delivered a fresh data drop (first onboarding or refresh)
- An existing customer added a new source system (e.g. previously CRM-only, now also SAP)
- A re-ingest is needed after a schema change in the source

Do not use:
- For partial corrections of one already-ingested table (use `scripts/ingest.py` directly)
- To re-run `generate_column_usage.py` after a manual data fix (run the script directly)
- To write or modify views (that's `build-ontology`)
- To classify derived dimensions (that's `extend-ontology`)

## Orient before acting

Before doing anything, check what state the warehouse is already in. This determines whether you're cold-starting or extending.

```bash
ls data/datasets/ 2>/dev/null              # any existing raw tables?
ls data/migrations/raw/ 2>/dev/null        # any migrations already declared?
ls data/datasets/*_columns.csv 2>/dev/null # any existing column shortlists?
test -f docs/INGEST_NOTES.md && echo "notes exist"
```

Three cases:

- **Cold start** (no raw tables, no migrations, no notes): proceed with the full procedure below — declare migrations first, then ingest.
- **Adding to an existing warehouse** (notes file present, some tables exist): read `INGEST_NOTES.md` end-to-end first. Treat this run as additive — declare migrations only for the *new* source tables, ingest only the new files, append to notes. Never edit existing migration files; if an existing source's schema is changing (upstream added a column), write a *new* numbered migration like `002_add_<column>.py` rather than editing `001_initial.py`. State up front to the user: "I see <N> tables already ingested. I'll add <M> new ones and append to `INGEST_NOTES.md`."
- **Re-ingesting a table that already exists**: ingestion validates the batch against the migrated schema and appends. If a clean slate is wanted, drop `data/datasets/<TABLE>/` first (the migration file stays put, and the runner will re-create the empty table on next run) — confirm with the user before deleting.

Never `cp` over an existing `INGEST_NOTES.md`. Append a dated section instead so prior context is preserved.

## Procedure

### 1. Inventory what was received

Before ingesting, list the input files and confirm the scope with the user.

```bash
ls -la <drop-directory>/
```

If `docs/INGEST_NOTES.md` does not exist, create it with a top-level `# Ingest notes` heading and a first dated section. If it does exist, append a new dated section — do not overwrite the file.

Write the inventory into the current section with:
- file name
- row count (use `wc -l` for CSV/TSV; for Excel, ingest into a scratch table to count)
- intended source-system name and table name (the directory name in `data/datasets/`)
- whether to ingest now, defer, or skip — and why

If the file list is ambiguous (cryptic names, no documentation), STOP and ask the user:

> "I see <N> files: <list>. Before I ingest, can you confirm the source system for each, the intended table name, and whether any should be skipped? Without this I'd be naming things wrong."

### 2. Declare each table's schema as a migration

For every new source table, write a `001_initial.py` migration **before** ingesting any data. The migration is what creates the empty Delta table; ingestion just appends batches that match the migrated schema. Without this step the ingest call fails with `Delta table for '<TABLE>' does not exist`.

```bash
mkdir -p data/migrations/raw/<TABLE>
cp .claude/skills/ingest-data/migration-template.py \
   data/migrations/raw/<TABLE>/001_initial.py
```

Open the migration and fill in `SCHEMA` based on the source file's columns. Use a quick Polars probe to see the column names and inferred types — this is a tool for the agent, not a runtime call:

```bash
uv run python -c "import polars as pl; df = pl.read_csv('path/to/<FILE>', try_parse_dates=True, infer_schema_length=10_000); print(list(df.schema.items()))"
```

Translate Polars dtypes to Delta `PrimitiveType` names (`pl.String` → `"string"`, `pl.Int64` → `"long"`, `pl.Float64` → `"double"`, `pl.Date` → `"date"`, `pl.Datetime` → `"timestamp"`, `pl.Boolean` → `"boolean"`).

Rules for the schema declaration:
- **Use the source-system column names verbatim.** Uppercase, raw codes, all of it. Renaming and decoding is the views layer (`build-ontology`).
- **Mark identifiers `nullable=False`.** Primary keys, business keys, foreign keys to other source tables. Everything else stays nullable — upstream systems frequently drop optional fields.
- **Pick the narrower type when in doubt.** `string` is the safest fallback if Polars guessed wrong; you can tighten later with a migration. But `string` for an obvious date or number defeats the purpose.
- **Do not edit `001_initial.py` after it has been applied in any environment.** Schema evolution is additive — new column? Write `002_add_<column>.py` using `dt.alter.add_columns([...])`.

Apply the migrations to materialize the empty Delta tables:

```bash
uv run python scripts/apply_delta_migrations.py
```

Output should list each new table as `applied 001 (001_initial.py)` and existing tables as `up-to-date`.

For each migration written, append a one-line entry to `docs/INGEST_NOTES.md` under a `## Migrations` heading: `<table>: <column count> columns, see data/migrations/raw/<table>/001_initial.py`.

### 3. Ingest one table at a time

Ingestion now appends against the migrated schema. The Delta table already exists (empty); your batches just need to match its declared shape.

```bash
uv run python scripts/ingest.py --file path/to/ORDERS.csv --table ORDERS
```

`scripts/ingest.py` submits to the backend's `ingest-file` task — start the backend first (`./start.sh`). For ad-hoc local ingestion without the backend, call `DeltaIngestionService.ingest()` directly from a small script (see `scripts/seed.py` for the pattern).

Rules:
- **Do not clean before ingestion.** Casting and decoding live in the views layer.
- **One Delta table per source entity.** If the customer ships one Excel file with many sheets, split them before ingesting.
- **Name tables after the source system** (e.g. `SD_SALESORD`, `CRM_ACCT`). The directory becomes `_raw_<NAME>` at read time.
- **Schema mismatches fail loud.** Missing columns, extra columns, uncastable values, nulls in `nullable=False` fields all raise. Fix by either correcting the source file (typical) or evolving the schema with a new migration (when the source genuinely changed).
- **Re-ingesting appends.** No silent overwrites; drop the table directory and re-run migrations if you need a clean slate.

For each ingest, append a one-line entry to `docs/INGEST_NOTES.md`: `<table>: <row count> rows, <column count> columns, source: <file>`.

### 4. List what's there

After all files are ingested:

```bash
uv run python scripts/warehouse_debug.py schema
```

Capture the output verbatim into `docs/INGEST_NOTES.md` under `## Schema after ingest`. This is the artifact `build-ontology` will start from.

### 5. Prune obviously-useless columns

```bash
uv run python scripts/generate_column_usage.py
```

This writes `data/datasets/<TABLE>_columns.csv` listing only columns worth keeping. It drops any column where:
- `cardinality = 0` (entirely NULL — no signal)
- `cardinality = 1 AND null_rate = 0` (constant — every row identical)
- Name ends with `_duplicated_0` (SAP export artifact)

The CSVs become the shortlist for the next phase. **Do not edit them by hand here** — the skill's job is to produce them, not curate them.

If the script reports unusually high prune rates on a table (e.g. >70% of columns dropped), call it out in `INGEST_NOTES.md` as a flag for the customer review meeting — it usually means the export was a wide-but-sparse SAP dump and the entity is real but the source format is noisy.

### 6. Surface data-quality flags worth telling the customer

While ingesting, watch for things `generate_column_usage.py` won't catch but a human would notice:

- **Duplicate primary keys** in a file that should have one row per entity
- **Mixed encodings** (UTF-8 vs Latin-1 mojibake)
- **Truncation indicators** (rows that look cut off, columns whose values are uniformly at the max length suggesting a VARCHAR limit was hit)
- **Date columns with `1900-01-01` or `9999-12-31`** sentinel values
- **Files that look like sample/test data** (very few rows, names like `_TEST`, `_SAMPLE`)

Each goes into `INGEST_NOTES.md` under `## Data-quality flags` with: table, column(s), what looks off, what would resolve it (a question for the customer or a re-export request).

### 7. Confirm before handoff

```bash
uv run python scripts/apply_delta_migrations.py   # confirms every table is at its declared version
uv run python scripts/warehouse_debug.py schema
ls data/datasets/*_columns.csv
```

The skill is done when:
- Every raw file the customer shipped has either been ingested or has a recorded reason it was skipped
- Every ingested table has a migration at `data/migrations/raw/<TABLE>/001_initial.py`
- `data/datasets/<TABLE>/` exists for every ingested table
- `data/datasets/<TABLE>_columns.csv` exists for every ingested table
- `docs/INGEST_NOTES.md` lists what was ingested, the post-ingest schema, the migrations written, and any data-quality flags
- `apply_delta_migrations.py` reports every table as up-to-date

Tell the user the next step is `build-ontology`, which will read `INGEST_NOTES.md` and the column CSVs to design entity views.

## What good looks like

- Every source table has a `001_initial.py` migration committed to git, declaring its schema
- Raw tables match the customer's files row-for-row (no silent cleaning)
- Every ingested table is listed in `INGEST_NOTES.md` with a row count and a pointer to its migration
- Column CSVs exist and are non-empty for every table that has any signal
- Data-quality flags are recorded so the customer review meeting has an agenda
- `apply_delta_migrations.py` is a no-op when re-run — every table is at its latest declared version

## What to avoid

- Cleaning, casting, or filtering data during ingestion — keep it raw, declare types in the migration
- Editing `001_initial.py` after it has been applied — write `002_*.py` instead
- Letting the ingestion service create a Delta table from inferred types — that path no longer exists; the migration must run first
- Designing views or making ontology decisions in this skill
- Skipping `INGEST_NOTES.md` — `build-ontology` and `review-ontology` both depend on it
- Combining multiple source entities into one Delta table — one table per entity
- Ingesting files the customer didn't intend to share (e.g. backup files in the drop directory) — confirm scope first
