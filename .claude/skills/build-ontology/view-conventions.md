# View conventions

Rules for writing DuckDB views that an LLM will query. Ordered by how often the agent makes mistakes when the rule is violated.

## The top comment

The parser reads consecutive `-- ...` lines at the top of the file as the view description. This block is injected into the agent's system prompt — everything else in the file is invisible to the LLM.

```sql
-- description: One row per sales order. Orders with customer, product, and delivery
-- status denormalized. Use for order volume, delivery performance, and per-customer
-- purchase history. Joins: customer_id -> customers; product_sku -> materials.
CREATE OR REPLACE VIEW sales_orders AS
...
```

- **Start with the grain.** `One row per <grain>.` is the single most useful phrase for an LLM. Without it, the LLM averages what it should sum and vice versa.
- **State the use case.** One sentence on what decisions this view supports.
- **State the joins.** Explicit foreign-key → target-view mappings reduce join errors dramatically.
- **State any pre-applied filters.** If the view is scope-gated or time-filtered, say so. The LLM will try to re-apply filters it sees from elsewhere — tell it not to.

## Filename ↔ view name

The filename stem must equal the view name. `customers.sql` contains `CREATE OR REPLACE VIEW customers AS ...`. The pre-commit lint (`scripts/check_ontology.py`) enforces this.

## Column naming

**Readable English. Underscore-separated. Units in the name.**

| Bad | Good |
|---|---|
| `ACCT_ID` | `customer_id` |
| `ord_tot` | `order_total_usd` |
| `dur` | `duration_minutes` |
| `wt` | `weight_kg` |
| `CRTD_DT` | `created_date` |
| `stat_cd` | `status` (after decoding) |
| `flag_active` | `is_active` (boolean assertion) |
| `late_ind` | `was_delivered_late` |

Text-to-SQL research (SNAILS, SIGMOD 2025) is blunt: LLMs hallucinate unit conversions when units are implicit, and they pick the wrong column when names are abbreviated. Spelling out names costs nothing at write time and eliminates a whole class of query errors.

## Consistent FK names across views

`customer_id` means the same thing in every view it appears in. If `customers.customer_id` is the PK, every fact view's FK to it must also be `customer_id`. Do not use `acct_id` in one view and `customer_id` in another.

When a fact view has a natural key from a different system that isn't interchangeable, name it differently — e.g. `sap_customer_id` to distinguish from the Salesforce `customer_id`. Don't conflate them just because they point at the same real-world entity.

## Decode status codes with CASE

```sql
CASE status_cd
  WHEN 'A' THEN 'active'
  WHEN 'I' THEN 'inactive'
  WHEN 'P' THEN 'pending'
END AS status
```

Never expose raw codes. The LLM doesn't know what `'A'` means and will invent explanations.

## Denormalize via JOINs

Every JOIN the LLM must construct is a potential error. Pre-join related entities. A `sales_orders` view that includes `customer_name` and `product_name` as columns is strictly better than three views the LLM must join manually.

```sql
CREATE OR REPLACE VIEW sales_orders AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    c.customer_country,
    o.product_sku,
    m.product_name,
    o.quantity,
    o.net_value_usd,
    CAST(o.order_date AS DATE) AS order_date
FROM _raw_SD_SALESORD o
LEFT JOIN _raw_CRM_ACCT c ON o.ACCT_ID = c.ACCT_ID
LEFT JOIN _raw_MM_MATMASTER m ON o.MATL_ID = m.MATL_ID;
```

## Pre-compute derived metrics

If the agent would need to write `SUM(CASE WHEN ...)`, `DATE_DIFF`, or a ratio to answer a common question, pre-compute it as a column. Every formula hidden in a view is one formula the LLM cannot get wrong.

Examples: `scrap_rate_pct`, `days_since_last_activity`, `quote_age_days`, `is_stalled`, `change_pct_vs_prior_period`.

## Cast types explicitly

```sql
CAST(x AS DATE), CAST(x AS INTEGER), x::DOUBLE
```

Polars inferred a type at ingestion; the view decides what the agent sees. Dates as strings are a common footgun — always cast.

## Filter noise in the view

The agent should never see rows it shouldn't query: inactive records, test accounts, internal-only rows, out-of-scope sales orgs. Apply the filter in the view, not via a column the agent must remember to check.

If the distinction matters (active vs. inactive, open vs. closed), expose it as a boolean on a single unified view rather than splitting into two views or requiring the agent to filter.

## Drop columns without ontological purpose

Not every source column belongs in a view. Omit:

- Audit timestamps that no business question references (`LAST_MOD_BY`, `ETL_LOADED_AT`)
- System-generated hashes and surrogate keys
- Columns that duplicate information already in another column
- Columns whose meaning you couldn't determine
- Any column whose cardinality was 1 (constant) or 0 (all NULL)

Every visible column is a potential distraction for the agent. Fewer, better columns > more, noisier columns.

## Scope gates

When the data spans multiple scopes but only one is in scope for this customer (a single sales org, a single plant, a single region), enforce the gate in the first view and have all dependent views filter against it:

```sql
-- customers.sql is the scope gate: only in-scope customers appear here.
CREATE OR REPLACE VIEW customers AS
SELECT ... FROM _raw_CRM_ACCT WHERE SALES_ORG = '<in-scope-org>';

-- cases.sql inherits the gate by filtering on customers.
CREATE OR REPLACE VIEW cases AS
SELECT ... FROM _raw_CRM_CASES
WHERE account_id IN (SELECT account_id FROM customers);
```

The production loader resolves view dependencies by retrying pending views until the set stops shrinking, so no explicit ordering is required. You can add a new gate view without updating any loader script.

## No NULLs in join keys

LLMs never write `WHERE fk IS NOT NULL`. If a FK is sometimes NULL in the source, either `COALESCE` to a sentinel at view time, or filter rows with NULL FKs out of the view. Never let the agent join on a nullable key unguarded.

## What to borrow from Kimball

- **One view per business process / entity.** A `sales_orders` fact view, a `customers` dimension view.
- **Conformed dimensions.** A single `customers` view referenced everywhere.
- **Additive measures.** `quantity`, `net_value_usd`, `duration_days` — columns the agent can `SUM`/`AVG` without thinking.

## What to discard from Kimball

- **Surrogate keys.** Force JOINs the LLM gets wrong. Use natural/business keys directly.
- **Slowly changing dimensions (SCD type 2).** LLMs forget `WHERE is_current`. Expose pre-filtered current-state views instead.
- **Snowflaking.** Never normalize dimensions into sub-dimensions. Keep views flat.

## Inline comments are for humans

After the top description block, anything you write is invisible to the LLM. Use inline comments to document decisions for future developers:

```sql
CREATE OR REPLACE VIEW customers AS
WITH active_aggregates AS (
    -- 2024+ transactor scope: customers appear here only if they have
    -- activity in the window. Dormant accounts are intentionally excluded
    -- per the scope decisions in ONTOLOGY_NOTES.md.
    SELECT sold_to_party, MIN(order_date) AS first_txn, ...
    FROM _raw_SD_SALESORD
    WHERE order_date >= DATE '2024-01-01'
    GROUP BY sold_to_party
)
SELECT ...
```

Keep the top block LLM-facing and concise. Move the rationale to inline comments.

## Checklist for a finished view

- [ ] Top comment starts with `-- description: One row per <grain>.`
- [ ] Filename stem matches the view name
- [ ] Uses `CREATE OR REPLACE VIEW`
- [ ] Every column is readable English with units
- [ ] Every status code is decoded
- [ ] Foreign-key names are consistent with other views
- [ ] Related entities are denormalized via JOIN
- [ ] Derived metrics are pre-computed
- [ ] Types are explicitly cast
- [ ] Noise rows are filtered out
- [ ] No source-system bookkeeping columns exposed
- [ ] Join keys are non-NULL
- [ ] `scripts/check_ontology.py` passes
- [ ] `scripts/check_views.py` compiles it and returns > 0 rows (unless zero is expected and noted)
