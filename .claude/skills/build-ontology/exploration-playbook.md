# Exploration playbook

Concrete probes for understanding a raw table. Work through them in order. Never `SELECT *` without a LIMIT; raw tables can be millions of rows wide and deep.

## Tooling

All three scripts connect directly to the Delta Lake tables under `data/datasets/` — no running backend needed.

| Script | Purpose |
|---|---|
| `scripts/warehouse_debug.py schema` | List all tables and views with column types and row counts |
| `scripts/warehouse_debug.py profile <table>` | Deep-dive one table: schema, sample, NULL rates, distributions |
| `scripts/warehouse_debug.py query "<SQL>"` | Ad-hoc SQL — use for PK checks, orphan checks, targeted counts |
| `scripts/generate_column_usage.py` | Auto-prune columns by cardinality heuristic, write CSV per table |
| `scripts/column_oracle.py` | LLM-assisted column interpretation (chinese-walled — raw values stay hidden from the human operator) |

## Step 0 — What did we get

```bash
uv run python scripts/warehouse_debug.py schema
```

Record, for your notes: every `_raw_<TABLE>`, its row count, its column count. A table with 5 columns and 1.2M rows is probably a junction/event table; one with 80 columns and 2k rows is probably an entity.

## Step 1 — The cardinality cull

```bash
uv run python scripts/generate_column_usage.py
```

Writes `data/datasets/<TABLE>_columns.csv` listing only columns that survive this filter:

- **Drop if `cardinality = 0`** → entirely NULL, nothing to query
- **Drop if `cardinality = 1 AND null_rate = 0`** → constant, every row identical, zero information
- **Drop if name ends with `_duplicated_0`** → SAP export artifact, not real data

Read the CSVs. That's your shortlist per table. Everything not in the CSV is not worth reasoning about.

**Important:** cardinality = 1 **with some NULLs** is kept intentionally. A column that's "active" on some rows and NULL on others is a weak boolean signal worth inspecting, not noise.

## Step 2 — Per-table profiling

For each shortlisted table that looks like an entity:

```bash
uv run python scripts/warehouse_debug.py profile _raw_<TABLE> --sample 20
```

Read, in order, what the command prints:

### Schema

Scan for columns that look like:
- **IDs** (suffixes `_ID`, `_NR`, `_NO`, names ending in `ID`): candidate keys — verify PK/FK in Step 3
- **Codes** (short text: 1-5 chars, suffixed `_CD`, `_TYP`, `_STAT`): need decoding
- **Dates/times**: will need `CAST AS DATE` in the view
- **Amounts/quantities**: check the unit — currency? piece count? weight?
- **Free text / notes**: usually drop unless you have a plan to extract something

### Sample rows

Scan for:
- **Columns that are always the same value** despite cardinality heuristic passing them through (sometimes cardinality = 2 where one value dominates 99% — check top values)
- **Columns that look like JSON or pipe-delimited** — may need to be split or unnested
- **Columns with timezone markers or mixed date formats**

### NULL rates

| Rate | Interpretation |
|---|---|
| 0.0 | Reliably populated — safe to require in WHERE clauses and JOINs |
| 0.01 - 0.3 | Mostly populated — safe to reference but document the gap |
| 0.3 - 0.7 | Half-populated — this is often a split-by-type column. Check if NULLs correspond to a category |
| 0.7 - 0.99 | Sparsely populated — probably a type-specific attribute. Consider whether the agent needs to know about it |
| 1.0 | Already dropped by Step 1 |

### Text column cardinality + top values

- **Distinct < 20 and evenly distributed** → enum, decode it in the view
- **Distinct ~= row count** → unique key candidate, verify in Step 3
- **Distinct << row count, top values dominate** → categorical with a long tail — decide if the tail matters

### Numeric ranges

Look at MIN/MAX/AVG:
- Negative values in an "amount" column → returns, credits, or a sign convention you need to understand
- MAX orders of magnitude higher than AVG → outliers or a mixed-type column (some rows are totals, some line items)
- Suspiciously round MIN (e.g. `0` on a weight column) → sentinel for "unknown", not a real zero

### Temporal ranges

Does the date range match what the customer told you? If they said "three years of data" and you see 2017-2024, either there's more history than expected or the field is not what you think. Note it in the questions section.

## Step 3 — Keys and relationships

### Verify primary keys

```sql
SELECT COUNT(*) AS rows, COUNT(DISTINCT <PK>) AS distinct_pks FROM _raw_<TABLE>
```

Equal → valid single-column PK. Unequal with small gap → check for NULLs in the PK column. Unequal with large gap → it's not actually a PK; try composite keys:

```sql
SELECT COUNT(*), COUNT(DISTINCT <A> || '|' || <B>) FROM _raw_<TABLE>
```

### Verify foreign keys

```sql
SELECT
  COUNT(*) AS total,
  COUNT(b.<PK>) AS resolved,
  ROUND(1.0 - COUNT(b.<PK>)::DOUBLE / COUNT(*), 3) AS orphan_rate
FROM _raw_A a LEFT JOIN _raw_B b ON a.<FK> = b.<PK>
```

- **orphan_rate < 0.01** — excellent, use the join freely
- **orphan_rate 0.01 - 0.1** — usable but document the gap
- **orphan_rate > 0.1** — investigate before relying on the join; likely a scope mismatch or wrong column

### Find dangling IDs

An ID column that looks important but resolves to nothing is usually safe to drop from the agent's view. Check all suspected IDs against all candidate tables before concluding they dangle.

## Step 4 — The oracle, for anything unclear

When profiling leaves you uncertain what a column *means* (vs. what's in it), use the oracle. It hides raw values from you — only the LLM sees them — and summarises.

```bash
# One focused question about specific columns:
uv run python scripts/column_oracle.py <TABLE> "Subtotal 2" "Net Value" \
    -q "Is Subtotal 2 the same as Net Value minus tax, or something else?"

# Batch profile every useful column in a table:
uv run python scripts/column_oracle.py <TABLE> --profile
```

Good uses:
- Ambiguous amount columns (which currency? which tax treatment?)
- Codes with no accompanying reference table
- Columns whose name is cryptic and whose values are themselves cryptic
- Suspected duplicate columns (is "Net Value" the same as "Amount"?)

Log the oracle's answer in `ONTOLOGY_NOTES.md` as an assumption the customer should confirm.

## Step 5 — Map entities to decisions

For each toolbox the customer will use, write down:

- What questions will users ask?
- What data supports each question?
- What metrics matter, and how are they derived?
- What thresholds are meaningful in this business?

This drives which computed columns to include (rates, aging, flags) and which JOINs to pre-apply. A view that only answers one question is too narrow; a view that tries to answer every question is too wide. Aim for one view per entity × one set of decisions.

## Column-level decision rubric

For each surviving column after Step 1, ask four questions. If the answer to any is clearly "no", drop the column from the view.

1. **Will the user ever ask about this?** If it's an ETL timestamp or system hash, no.
2. **Does it resolve to something meaningful?** If it's a dangling ID, no.
3. **Can the agent use it without hidden context?** Status codes need decoding; raw codes fail this test until decoded.
4. **Is it distinct from columns we're already keeping?** Two columns that always agree are one column plus noise.

## When to stop exploring

You're ready to move to Phase 3 (write views) when you can answer, for each raw table:

- What real-world entity does this table represent?
- Does it deserve its own view, or should it be joined into another view?
- What is the grain of each intended view?
- Which columns will that view expose, under what names?
- Which status codes need decoding, into what human-readable values?
- Which JOINs denormalize related entities?
- What scope gates or filters apply?

If any of those are still "I'm not sure", write the question in `ONTOLOGY_NOTES.md` and either probe more or flag it for the customer review meeting.
