# Ontology Definition Guide

This document defines what an **ontology** means in Fulcrum Chat and serves as the
working prompt for building one when onboarding a new customer.

---

## What is an ontology?

An ontology is the **semantic layer between raw customer data and the AI agent**. It
answers: "what entities exist in this business, what do they mean, and how do they
relate?"

We borrow this concept from Palantir Foundry, where the ontology is the typed object
graph that sits above raw datasets and becomes the single API that all applications and
agents consume. Our version is smaller in scope but follows the same core principles:

| Palantir concept | Fulcrum equivalent |
|---|---|
| Object type | A named DuckDB view over raw Delta Lake tables |
| Properties | View columns with human-readable names and types |
| Link types | JOIN clauses in views that denormalize related entities |
| Object descriptions | `-- description:` comment on the first non-whitespace line of each `.sql` file |
| Ontology SDK | `build_schema_instructions()` — injects the schema into the LLM system prompt |
| Actions | Agent tools (`execute_sql`, toolbox-specific tools) |

### Design principles

1. **Decision-first modeling** (Palantir). Don't mirror the source schema — model the
   entities and relationships that support the decisions users actually need to make.
2. **Objects, not tables** (Palantir). The agent should think in terms of customers,
   orders, and machines — never in terms of `CRM_ACCT` or `PP_PRODORD`.
3. **One ontology per customer.** Each customer deployment has its own set of views,
   prompts, and tools that together form a coherent ontology.
4. **The ontology is the contract.** Tools query views. Signals are generated from views.
   If it's not in the ontology, the agent can't see it.
5. **Pre-join, don't normalize** (anti-Kimball snowflake). Every JOIN the LLM must
   construct is a potential error. Pre-join related entities into flat, wide views.
6. **Pre-compute, don't delegate** (metrics layer). If the agent needs `churn_rate` or
   `quote_conversion_pct`, define it as a column. Every formula hidden in a view is one
   formula the LLM cannot get wrong.

---

## View design rules

These rules are optimized for an LLM writing SQL. They borrow selectively from Kimball
dimensional modeling, Palantir's ontology approach, and text-to-SQL research (SNAILS,
SIGMOD 2025; synthetic column descriptions, arXiv 2408.04691).

### What to borrow from Kimball

- **One view per business process / entity.** A `sales_orders` fact view, a `customers`
  dimension view. This maps cleanly to how LLMs pick which view to query.
- **Conformed dimensions.** A single `customers` view referenced everywhere. The column
  `customer_id` means the same thing in every view. This eliminates ambiguity.
- **Additive measures in fact views.** `quantity`, `total_value_usd`, `duration_minutes`
  — columns the agent can SUM/AVG without needing to understand the formula.

### What to discard from Kimball

- **Surrogate keys.** Force JOINs that LLMs get wrong (wrong key column, wrong
  direction). Use natural/business keys directly.
- **Slowly changing dimensions (SCD type 2).** LLMs reliably forget `WHERE is_current`
  filters. If you need historical records, expose a pre-filtered view of current state.
  Never expose SCD bookkeeping columns.
- **Snowflaking.** Never normalize dimensions into sub-dimensions. Keep views flat.

### LLM-specific rules

These are empirically backed by text-to-SQL research:

1. **Spell out column names.** `order_total_usd` not `ord_tot`. Never abbreviate.
   Underscore-separated words outperform camelCase.

2. **Include units in the name.** `revenue_usd`, `duration_days`, `weight_kg`. LLMs
   hallucinate unit conversions when units are implicit.

3. **State the grain in the description.** The single most useful metadata for an LLM.
   Format: `One row per <grain>. <What this view is for>.`
   ```
   -- description: One row per sales order. Orders with customer and product details, delivery status.
   ```

4. **Fewer views is better.** Pre-join frequently co-queried entities. A
   `sales_orders` view that already includes `customer_name` and `product_name` is
   better than three views the LLM must join. Every JOIN is an error surface.

5. **Pre-compute derived metrics.** `scrap_rate_pct`, `days_since_last_activity`,
   `is_churned`. Never make the LLM write `SUM(CASE WHEN ...)` or complex date math.

6. **Use readable string values, not codes.** `status = 'Delivered'` not
   `status_cd = 'DLVD'`. Decode all enums in the view via CASE expressions.

7. **Boolean columns should read as assertions.** `is_active`, `has_open_quotes`,
   `was_delivered_late` — not `flag_active = 1` or `late_ind = 'Y'`.

8. **No NULLs in join keys.** LLMs never add `IS NOT NULL` guards. Enforce this in
   the view with `WHERE` or `COALESCE`.

9. **Filter away noise in the view.** Inactive records, test data, internal accounts.
   The agent should never see rows it shouldn't query. If the agent needs to distinguish
   active vs. inactive, expose it as a boolean column on a single view rather than
   requiring a filter.

10. **Drop columns that have no ontological purpose.** Not every source column belongs
    in a view. Internal audit timestamps, ETL bookkeeping fields, system-generated
    hashes, and columns that no business question would ever reference are noise.
    Every column the agent can see is a column it might query — unnecessary columns
    increase the chance of confusion and hallucinated filters. Only include a column
    if it supports a decision the user might make or a question the agent might need
    to answer.

---

## What comprises an ontology?

An ontology in Fulcrum has **four components**:

### 1. Semantic views (`data/datasets/views/*.sql`)

SQL views that reshape raw Delta Lake tables into agent-friendly entities. Each view:

- Has a `-- description:` comment on the first non-whitespace line explaining what it represents
- Uses `CREATE OR REPLACE VIEW <name> AS SELECT ...`
- Renames cryptic source columns to readable names (`ACCT_ID` -> `customer_id`)
- Decodes status codes into human-readable values via `CASE` expressions
- Adds computed columns where useful (`scrap_rate_pct`, `days_since_activity`)
- JOINs related raw tables to denormalize (e.g. orders joined with customer names)
- Filters to relevant records (e.g. `WHERE status = 'A'` for active accounts only)

When views exist, the system hides raw `_raw_*` tables from the agent entirely.

### 2. Prompts (`backend/prompts/`)

Markdown files loaded at runtime that tell the agent how to behave in each toolbox:

- **`system.md`** — Shared persona, tone, and company context
- **`{toolbox}.md`** — Toolbox-specific instructions: the user's role, domain reasoning
  guidance, how to interpret metrics, what actions to recommend

Prompts should reference the ontology in domain terms ("look at the customer's recent
orders and quote pipeline") rather than hard-coding view names.

### 3. Toolbox tools (`backend/customer/tools/__init__.py`)

The set of agent tools available per toolbox. `execute_sql` is the primary read path.
Additional tools can be toolbox-specific (e.g. `create_quote` for Sales).

### 4. View descriptions (embedded in `.sql` files)

The `-- description:` line is extracted at load time and injected into the agent's system
prompt. Always **state the grain first**, then describe the content and when to use it:

| Weak | Strong |
|---|---|
| `Customer data` | `One row per customer. Active accounts with tier, state, and assigned sales rep.` |
| `Sales orders table` | `One row per sales order. Orders with customer and product details, delivery status.` |
| `Purchase history` | `One row per customer per product per month. Use for baseline comparisons and churn detection.` |

---

## How the ontology flows to the agent

```
data/datasets/views/*.sql
        |
        v
DuckDBWarehouse._load_sql_views()     -- parses name, description, executes SQL
        |
        v
DuckDBWarehouse.list_tables()         -- returns list[TableInfo] (views only, hides raw)
        |
        v
build_schema_instructions(tables)     -- renders markdown: name, description, columns
        |
        v
system.md + {toolbox}.md + schema     -- composed into final system prompt
        |
        v
Agent sees: persona + domain instructions + "## Available Data Tables" with full schema
```

---

## The onboarding workflow

The process has three phases:

1. **Ingest** — get the customer's raw data into Fulcrum as-is
2. **Explore + draft** — AI-assisted exploration produces a best-guess ontology plus
   documented assumptions and open questions
3. **Customer review** — walk through the open questions with the customer, fill gaps,
   and produce the first deployable ontology they can test

---

## Phase 1: Data ingestion

**Goal:** Get the customer's raw data into Fulcrum as Delta Lake tables so it can be
explored.

**Input:** Data files from the customer — CSV, TSV, Excel (.xlsx/.xls/.xlsm), or
existing Parquet/Delta exports.

### How ingestion works

Fulcrum uses `DeltaIngestionService` (Polars + deltalake) to convert source files into
Delta Lake table directories under `data/datasets/`. Each directory contains Parquet data
files and a `_delta_log/` folder. DuckDB discovers these at startup and creates
`_raw_<DIRECTORY_NAME>` views via `delta_scan()`.

**Two ingestion paths:**

1. **CLI script** (for bulk initial load):
   ```bash
   uv run python scripts/ingest.py --file path/to/orders.csv --table SD_SALESORD
   ```
   Posts to the running backend API at `/internal/tasks/ingest-file`.

2. **Seed script** (template dev only):
   ```bash
   uv run python scripts/seed.py
   ```
   Generates synthetic data, writes CSVs to a temp dir, then ingests each as Delta.

### Ingestion decisions

Before ingesting, determine:

- **Table naming.** Use the source system's table name if known (e.g. `SD_SALESORD`,
  `CRM_ACCT`). If the customer provides friendly names, use those — the views will
  rename everything anyway. The directory name under `data/datasets/` becomes the raw
  table name prefixed with `_raw_`.

- **One file per table vs. multiple files.** If the customer provides one CSV per entity,
  each becomes its own Delta table. If they provide a single export with multiple sheets,
  split them before ingestion. Re-ingesting the same table name appends with schema merge.

- **Schema preservation.** Polars infers types from the source file. Don't pre-process
  or clean the data — ingest it as-is. The semantic views handle all type casting,
  renaming, and filtering. Keep the raw layer as a faithful copy of what the customer
  gave us.

---

## Phase 2: AI-assisted exploration and ontology creation

**Goal:** Explore the ingested raw data and produce a complete ontology — views, prompts,
tools, and documentation of what we assumed and what we still need to ask.

This phase is designed to be done with an AI coding assistant. The assistant should
explore the data systematically without reading full data files (which could be huge)
and produce all ontology artifacts.

### Quick start with `warehouse_debug.py`

Before writing manual SQL, use the warehouse debug CLI to explore ingested data. It works
offline (no running backend) — instantiates DuckDB directly against `data/datasets/`.

```bash
# Step 1: Discover what's there — tables, columns, row counts
uv run python scripts/warehouse_debug.py schema

# Step 2: Profile a table or view — sample rows, NULL rates, distributions
uv run python scripts/warehouse_debug.py profile _raw_SD_SALESORD
uv run python scripts/warehouse_debug.py profile customers --sample 20

# Ad-hoc queries — verify PKs, test joins, check orphans
uv run python scripts/warehouse_debug.py query "SELECT COUNT(*), COUNT(DISTINCT ACCT_ID) FROM _raw_CRM_ACCT"
uv run python scripts/warehouse_debug.py query "SELECT * FROM _raw_SD_SALESORD LIMIT 5"
```

Use `schema` output as the starting point, then `profile` each table, then `query` for
the specific checks described in the exploration steps below.

### Exploration strategy

Raw data can be large — never `SELECT *` without a LIMIT, never dump entire tables. Use
targeted queries to understand structure and content efficiently.

#### Step 1: Discover what's there

```sql
-- List all ingested raw tables
SELECT table_name FROM information_schema.tables
WHERE table_name LIKE '_raw_%';

-- For each table, get columns and types
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = '_raw_<TABLE>'
ORDER BY ordinal_position;

-- Row count per table
SELECT COUNT(*) FROM _raw_<TABLE>;
```

Record: table names, column counts, row counts, column names and types.

#### Step 2: Sample and profile each table

For each raw table:

```sql
-- Sample rows to understand the data shape
SELECT * FROM _raw_<TABLE> LIMIT 10;

-- For text columns: distinct values (or top N if high cardinality)
SELECT <COL>, COUNT(*) as n FROM _raw_<TABLE>
GROUP BY <COL> ORDER BY n DESC LIMIT 20;

-- For numeric columns: range and distribution
SELECT MIN(<COL>), MAX(<COL>), AVG(<COL>::DOUBLE), COUNT(DISTINCT <COL>)
FROM _raw_<TABLE>;

-- For date columns: range
SELECT MIN(<COL>), MAX(<COL>) FROM _raw_<TABLE>;

-- NULL rates
SELECT
    COUNT(*) AS total,
    COUNT(<COL>) AS non_null,
    ROUND(1.0 - COUNT(<COL>)::DOUBLE / COUNT(*), 3) AS null_rate
FROM _raw_<TABLE>;
```

Record: what each column appears to contain, cardinality, value ranges, NULL prevalence.

#### Step 3: Identify entities and relationships

From the profiling, identify:

- **Entities**: What real-world things does each table represent? A table with columns
  like `ACCT_ID, ACCT_NM, ADDR, PHONE` is clearly a customer/account table.
- **Primary keys**: Which column(s) uniquely identify a row? Verify:
  ```sql
  SELECT COUNT(*), COUNT(DISTINCT <PK_COL>) FROM _raw_<TABLE>;
  -- If equal, it's a valid PK
  ```
- **Foreign keys**: Which columns reference other tables? Look for shared column names
  or ID patterns across tables. Verify the join works:
  ```sql
  SELECT COUNT(*) FROM _raw_A a
  LEFT JOIN _raw_B b ON a.<FK> = b.<PK>
  WHERE b.<PK> IS NULL;
  -- Orphan count — should be 0 or explainably small
  ```
- **Code columns**: Columns with a small set of cryptic values (`COMP`, `WIP`, `HOLD`)
  are status/type codes that need decoding.

#### Step 4: Map to business decisions

For each toolbox the customer will use, ask:

- What questions will users ask? ("Which accounts are at risk of churning?")
- What data supports those questions? (purchase trends, quote activity, order history)
- What metrics matter? (revenue by customer, yield rate, quote conversion rate)
- What thresholds are meaningful? ("No orders in 90 days = at risk")

This drives which computed columns and which JOINs to include in the views.

### Producing the ontology artifacts

Based on the exploration, produce:

#### Semantic views

For each identified entity, write a `.sql` file in `data/datasets/views/`:

```sql
-- description: <What this entity is and when the agent should query it>
CREATE OR REPLACE VIEW <entity_name> AS
SELECT
    <source_col>    AS <readable_name>,
    ...
FROM _raw_<TABLE> t
LEFT JOIN _raw_<RELATED> r ON t.<FK> = r.<PK>;
```

Follow these rules:
- **Name views** after business entities (plural): `customers`, `sales_orders`, `machines`
- **Rename all columns** from source codes to readable English
- **Decode status codes** with CASE expressions
- **Denormalize** common lookups via JOINs — the agent should never need to join manually
  for name resolution
- **Add computed columns** for derived metrics (rates, percentages, durations, aging)
- **Cast types** explicitly — `CAST(x AS DATE)`, `CAST(x AS INTEGER)`
- **Filter noise** — exclude inactive records, test data, internal-only rows
- **Drop purposeless columns** — omit audit timestamps, ETL fields, system hashes, and
  anything no business question would reference. Every visible column is a potential
  distraction for the agent.
- **Use consistent FK names** across views: `customer_id` everywhere, not `acct_id`
  in one view and `customer_id` in another

#### Toolbox prompts

Write `backend/prompts/{toolbox}.md` with domain-specific guidance. Reference entities
by their business names, not view names. Include reasoning guidance:
- How to interpret key metrics
- What thresholds signal risk or opportunity
- What actions to recommend in common scenarios

#### Tool configuration

In `backend/customer/tools/__init__.py`, assign tools per toolbox. Every toolbox gets
`execute_sql` at minimum. Add custom tools if the customer needs write-back actions.

### Documenting assumptions and open questions

During exploration, **always** produce a `docs/ONTOLOGY_NOTES.md` file. This file
captures what we decided, what we assumed, and what we still need to confirm with the
customer.

Structure:

```markdown
# Ontology Notes — <Customer Name>

## Entity summary

| View | Source tables | Description | Row count |
|---|---|---|---|
| customers | _raw_CRM_ACCT | Active customer accounts | 1,234 |
| sales_orders | _raw_SD_SALESORD, _raw_CRM_ACCT, _raw_MM_MATMASTER | Orders with customer and product details | 45,678 |
| ... | ... | ... | ... |

## Entity relationships

- customers.customer_id <- sales_orders.customer_id (1:many)
- customers.customer_id <- quotes.customer_id (1:many)
- products.sku <- sales_orders.product_sku (1:many)
- ...

## Assumptions

Document every assumption made during ontology creation. Each assumption should be
something we could be wrong about and that the customer should confirm.

- [ ] `STAT_CD = 'A'` means active account — we filter to only active in the
      `customers` view. Confirm with customer.
- [ ] `RSN_CD` values decoded based on patterns in the data (`MECH_FAIL` = mechanical
      failure). Need the official code table from the customer.
- [ ] `TIER_CD` values (Gold/Silver/Bronze) appear to be customer tiers. Is this
      current or could it be stale?
- [ ] `OWN_REP` / `SLS_REP` columns contain rep IDs like `SR-01`. No rep master table
      was provided — we can't resolve to names. Ask customer for a rep roster.
- [ ] Monthly purchase history (`CRM_PURCH_HIST`) has a `PERIOD` column as YYYY-MM
      strings. Assumed this is the invoice month, not the order month.

## Open questions

Things we couldn't determine from the data alone and need customer input on.

- What do the status codes in `PP_PRODORD.ORD_STATUS` mean? We see COMP/WIP/HOLD —
  guessed Completed/In Progress/On Hold.
- Are there additional data sources we should expect? (e.g. a rep/employee table,
  a plant/facility table)
- What date range does the data cover? Is it a full extract or a recent window?
- Are there records we should exclude? (test accounts, internal orders, etc.)
- What KPIs does management track? We built computed columns for yield, scrap rate,
  and quote aging — are there others?

## Data quality observations

Issues spotted during profiling that the customer should be aware of.

- `_raw_SD_SALESORD.REQ_DT` has 12 NULL values (0.3%) — orders with no requested
  delivery date
- `_raw_CRM_QUOTES.VALID_UNTIL` has dates in the past for 34 open quotes — possibly
  stale data
- `_raw_PP_PRODORD.ACT_END` has empty strings instead of NULLs for in-progress orders
```

---

## Phase 3: Customer review

**Goal:** Walk through `ONTOLOGY_NOTES.md` with the customer, resolve open questions,
and produce the first deployable ontology.

**Input:** The draft ontology (views, prompts, tools) and the notes file from Phase 2.

### The review meeting

Share `ONTOLOGY_NOTES.md` with the customer. Go section by section:

1. **Entity summary.** "Here's what we found in your data and how we've modeled it.
   Does this match how you think about your business?" Look for missing entities
   (did they forget to send a table?) and misnamed entities (do they say "work orders"
   not "production orders"?).

2. **Assumptions.** Walk through each checkbox. The customer confirms, corrects, or
   says "I need to check." For each:
   - Confirmed → check the box, update the view if wording changed
   - Corrected → update the view, check the box, note what changed
   - Unknown → leave unchecked, mark as still open

3. **Open questions.** These are the gaps the AI couldn't fill from data alone. The
   customer provides code tables, explains business logic, identifies exclusions.
   Every answer should result in a concrete view change or prompt update.

4. **Data quality.** Flag issues and let the customer decide: is this expected, is it
   a data bug on their side, or should we handle it in the view?

### After the review

- Update views based on customer feedback
- Update prompts if domain terminology changed
- Move resolved assumptions from "Assumptions" to a "Resolved" section (keep the
  record — don't delete)
- Move answered questions out of "Open questions"
- Re-run the ontology checklist

The result is a deployable ontology. The customer can start testing with real questions.
Iterate from here — the first version won't be perfect, but it will be grounded in real
data and confirmed assumptions rather than guesswork.

---

## Ontology checklist

Before considering an ontology complete:

- [ ] All raw tables have corresponding semantic views (no raw data exposed to agent)
- [ ] Every view has a meaningful `-- description:` on the first non-whitespace line
- [ ] Column names are readable English, not source system codes
- [ ] Status codes are decoded to human-readable values
- [ ] Common lookups are denormalized (no manual JOINs needed for name resolution)
- [ ] Computed metrics are included where useful (rates, durations, aging)
- [ ] Column names are consistent across views (`customer_id` everywhere)
- [ ] Types are explicitly cast (dates, numbers)
- [ ] Inactive/test records are filtered out
- [ ] Toolbox prompt references the domain correctly
- [ ] `TOOLBOX_TOOLS` has the right tools assigned
- [ ] `ONTOLOGY_NOTES.md` exists with assumptions, open questions, and data quality notes
- [ ] Agent can answer representative user questions correctly
- [ ] `check_customer_config.py` passes

---

## Example view

```sql
-- description: One row per customer. Active accounts with tier, state, and assigned sales rep.
CREATE OR REPLACE VIEW customers AS
SELECT
    a.ACCT_ID    AS customer_id,
    a.ACCT_NM    AS customer_name,
    a.ST_CD      AS state,
    a.TIER_CD    AS tier,
    CAST(a.CRTD_DT AS DATE) AS customer_since,
    a.OWN_REP    AS sales_rep_id
FROM _raw_CRM_ACCT a
WHERE a.STAT_CD = 'A';
```

This view:
- Renames all columns from SAP-style codes to English
- Filters to active accounts only (assumption documented in `ONTOLOGY_NOTES.md`)
- Casts the date column explicitly
- Keeps `sales_rep_id` as an ID because no rep master table exists (open question)
