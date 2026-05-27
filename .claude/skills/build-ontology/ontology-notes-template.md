# Ontology Notes — <Customer Name>

Keep this file updated as exploration proceeds. Every assumption, every decoded code, every scope decision that isn't self-evident from the data belongs here. This is the document the customer reviews in Phase 3.

## Entity summary

One row per modeled entity. Fill in as views are written.

| View | Source tables | Description | Row count |
|---|---|---|---|
| <view_name> | _raw_<TABLE>, _raw_<OTHER> | <one-line description> | <N> |

## Entity relationships

Describe the shape of the graph. Mark cardinality (1:1, 1:many, many:many).

- `customers.customer_id` ← `sales_orders.customer_id` (1:many)
- `products.sku` ← `sales_orders.product_sku` (1:many)

## Scope decisions

Pre-applied filters that narrow the data beyond what's in the raw tables. The customer must confirm each.

- **Sales org / region / plant filter**: <what we filtered to, and why>
- **Time window**: <e.g. 2024+ on transactional views; master data unfiltered>
- **Active-only filter**: <e.g. `STAT_CD = 'A'` on accounts>

## Assumptions

Every item is something we decided from data alone and could be wrong about. Customer confirms in the review meeting.

- [ ] `STAT_CD = 'A'` means active — we filter to active-only in `customers`. Confirm.
- [ ] `RSN_CD` decoded from patterns in the data (`MECH_FAIL` = mechanical failure). Need the official code table.
- [ ] `TIER_CD` (Gold/Silver/Bronze) interpreted as customer tier. Is this current or could it be stale?
- [ ] Monthly purchase history `PERIOD` column is YYYY-MM. Assumed to be invoice month, not order month.

## Open questions

Things we could not determine from the data alone.

- What do the status codes in `PP_PRODORD.ORD_STATUS` mean? We see COMP/WIP/HOLD — guessed Completed/In Progress/On Hold.
- Are there additional data sources we should expect? (rep/employee table, plant/facility table, FX rate table)
- What date range does the data cover — is it a full extract or a recent window?
- Are there records we should exclude? (test accounts, internal orders, demo data)
- What KPIs does management track? We computed <list> — are there others?
- Multi-currency: data contains <currencies>. How should we handle cross-currency aggregates?

## Data quality observations

Issues spotted during profiling that the customer should be aware of.

- `_raw_SD_SALESORD.REQ_DT` has N NULL values (X%) — orders with no requested delivery date
- `_raw_CRM_QUOTES.VALID_UNTIL` has past dates for M open quotes — possibly stale
- `_raw_PP_PRODORD.ACT_END` has empty strings instead of NULLs for in-progress orders
- Orphan rate on `<FK>` join is X% — <hypothesis>

## Decoded codes

Running table of status/type codes we decoded, with our interpretation. Each row is effectively an assumption.

| Source column | Raw value | Decoded to | Confidence | Notes |
|---|---|---|---|---|
| `STAT_CD` | `A` | `active` | high | Obvious from sample |
| `ORD_STATUS` | `COMP` | `completed` | medium | Guessed from pattern |
| `ORD_STATUS` | `WIP` | `in_progress` | medium | Guessed |
| `ORD_STATUS` | `HOLD` | `on_hold` | medium | Guessed |

## Resolved

Items the customer has confirmed or corrected after the review meeting. Move assumptions and open questions here as they're settled — keep the history, don't delete.

- [x] `STAT_CD = 'A'` confirmed as active. (resolved YYYY-MM-DD)
