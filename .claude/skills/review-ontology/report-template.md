# Ontology Review — <YYYY-MM-DD>

Point-in-time snapshot. Overwritten on each review run. Do not hand-edit — let the review skill regenerate.

## Use cases reviewed against

The ontology was evaluated against these stated use cases, extracted from `backend/prompts/`, `docs/ONTOLOGY_NOTES.md`, and `backend/customer/queries.py`:

1. <use case 1 — one sentence>
2. <use case 2 — one sentence>
3. <use case 3 — one sentence>
4. ...

Every finding below ties back to one of these or to a rule in `docs/ontology.md` / `view-conventions.md`.

## Summary

<One paragraph. Overall health. Count of findings per severity. Top 3 things to fix first.>

- Blockers: N
- Coherence: N
- Convention: N
- Suggestion: N

**Fix first:**
1. <highest-impact finding, one line>
2. <next, one line>
3. <next, one line>

## Blockers

Ontology is broken or contradicts itself. Fix before anything else.

### <Finding title>
- **Location**: `path/to/file.sql:LN`
- **Issue**: <one sentence>
- **Use case impacted**: <which use case this breaks>
- **Fix**: <describe the change, not code>

<repeat per blocker>

## Coherence

View, prompt, and use cases disagree, or meta-information reaches the agent.

### <Finding title>
- **Location**: `path/to/file:LN`
- **Issue**: <one sentence>
- **Why it matters**: <which use case or rule>
- **Fix**: <describe>

<group by root cause where possible — if six views have the same leak, one finding with six locations>

## Convention

Violates `view-conventions.md` but agent can probably still work. Can be batched.

### Column naming
- `views/foo.sql` column `ord_tot` → suggest `order_total_usd`
- `views/bar.sql` column `dur` → suggest `duration_minutes`

### Undecoded codes
- `views/baz.sql` column `status` exposes raw values `A`/`I`/`P` — add CASE decode

<...>

## Suggestion

Improvements, not fixes.

- <suggestion, one line>
- <suggestion, one line>

## Column-level profiling notes

Tables below reflect live profiling output. Used to drive column-value findings above. Kept here for traceability.

### <view_name>
| Column | NULL % | Cardinality | Judgement |
|---|---|---|---|
| customer_id | 0% | ~unique | keep (join key) |
| legacy_ref | 82% | 12 | **flag** — high NULL, no use case |
| audit_stamp | 0% | ~unique | **flag** — ETL bookkeeping, drop |
| ... | ... | ... | ... |

<repeat per view>

## Validator output

**Omit this section entirely if all three validators passed.** Only include when there is actual failure to report.

Captured verbatim from:

```
uv run python scripts/check_ontology.py
uv run python scripts/check_views.py
uv run python scripts/check_customer_config.py
```

<paste output — truncate at ~50 lines if long>

## Meta-information grep

**Omit this section entirely if no hits landed in agent-visible text.** On a clean ontology the grep output is all benign `FROM _raw_` SQL references; printing them adds noise.

Include only when one or more hits became Coherence findings above.

```
<grep output for hits that were flagged>
```

## What was not reviewed

Be explicit about scope limits:

- <e.g. "new view X was added but no use case documentation existed — flagged as an open question for the user">
- <e.g. "production toolbox prompts were not covered because no production views exist yet">
