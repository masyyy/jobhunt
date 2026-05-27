# <dimension_name>

**Class:** `Precomputed-deterministic` | `Precomputed-ML` | `Semantic-search`
**Refresh:** `daily` | `weekly` | `on-ingest`
**Task:** `<task_function_name>`
**Tool (semantic-search only):** `<tool_name>`

## Use case

One paragraph: which use case (from prompts / ONTOLOGY_NOTES) this dimension serves. State the agent question this enables. If the recipe doesn't earn a use case, it doesn't earn a place.

## Inputs

List every view (or raw table, exceptionally) the task reads from. For each, name the columns consumed.

```
- customers (sap_customer_id, country, industry)
- assets (sap_customer_id, machine_type, install_year)
- sales_line_items (sap_customer_id, material_category, net_value, order_date)
```

If inputs are not yet exposed as views, that's a build-ontology gap — flag it before scaffolding the recipe.

## Output schema

Schema of the Delta table the task writes to. Include types, nullability, and primary key. **Documentation only** — the executable schema lives in the migration files (see `## Migrations` below). Keep this in sync; `review-ontology` flags drift.

```
- sap_customer_id (str, NOT NULL, PK)
- peer_group_id (int, NOT NULL)
- similarity_score (float, NULL allowed)
- computed_at (timestamp, NOT NULL)
```

For semantic-search recipes, describe the index schema instead:

```
- entity_id (str, NOT NULL) — FK back to the entity view
- embedding (vector<float, 1536>) — output of <embedding model>
- text_chunk (str) — the chunked text that was embedded
- chunk_index (int) — position within the source document
```

## Migrations

Delta schema is materialized by numbered migration files at:

```
data/migrations/derived/<dimension_name>/
  001_initial.py     # creates the table with the schema above
  002_<change>.py    # additive changes (add column, etc.)
```

The runner (`scripts/apply_delta_migrations.py`) applies pending migrations and stamps the version on the Delta table itself. It runs on deploy (`entrypoint.sh`) and at local startup (`start.sh`), so the table exists before tasks or views need it.

## Algorithm

Describe what the task should compute. Be concrete enough that an engineer can start coding.

For **Precomputed-deterministic**: the formula or query plan.

> Build a co-purchase pair table by self-joining `sales_line_items` on `offer_id`, counting distinct customers per (material_a, material_b) pair, filtering pairs with support < 5.

For **Precomputed-ML**: a starting algorithm, flagged as placeholder.

> *Placeholder — engineer chooses.* Suggested start: k-means on standardized features `(country, machine_type_count, total_spend_log, age_years)`. Choose k by silhouette on a held-out fold. Re-evaluate against DBSCAN if cluster sizes are imbalanced.

For **Semantic-search**: the chunking strategy and embedding model placeholder.

> *Placeholder — engineer chooses.* Suggested start: `text-embedding-3-small`, chunk by paragraph (max 500 tokens, 50-token overlap), one row per chunk, FK back to source entity. Validate retrieval quality on 20 hand-labeled queries before going to production.

## Refresh cadence and concurrency

How often the task runs and what locks it needs.

```
- Cadence: weekly (Monday 03:00 UTC)
- queueing_lock: <name> (so two refreshes can't queue simultaneously)
- lock: <name> (so a refresh can't run while a downstream consumer is mid-query)
- Estimated runtime: <minutes>
```

If unsure, leave a note for the engineer to measure on first run.

## Consumed by

How the agent actually uses this dimension. Cite the consuming view or tool, and the use case.

```
- View: customers_with_peers (joins peer_group_id back into customers)
- Use case: UC1 expected-spend baseline (peer median spend = expected for customer)
```

For semantic-search:

```
- Tool: semantic_search_cases
- Use case: Service Support Sarah (find similar past cases by description)
- Use case: parts identification (resolve part from descriptive text)
```

## Validation

What "this dimension is working" looks like. The engineer needs a way to know they're done.

```
- Output table is non-empty after first run
- All sap_customer_ids in customers are present in customer_peer_groups (LEFT JOIN, no NULLs)
- Peer groups are roughly balanced (no group has >50% of customers, none has <2 customers)
- Manual spot-check: customers in the same group share machine type and country
```

## Open questions

Anything the engineer needs to clarify with the customer or product before implementing.

```
- Should peer groups respect sales-org boundaries, or cross-region?
- Confidence/similarity score — does the agent surface it to the user, or only use it to filter?
- Refresh on a schedule, or trigger after each ingest?
```

## Status

```
- [ ] Recipe written
- [ ] Initial migration written and applied (table exists with declared schema, zero rows)
- [ ] Task stub registered
- [ ] Wrapping view compiles
- [ ] Algorithm implemented
- [ ] First run produced data
- [ ] Validation passed
- [ ] Wrapping view returns rows in production
- [ ] Prompt updated to reference the dimension
```
