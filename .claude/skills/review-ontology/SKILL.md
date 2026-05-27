---
name: review-ontology
description: Audit an existing Fulcrum ontology (views + prompts + notes + derived dimensions) for coherence against its stated use cases. Read-only — produces a findings report in docs/ONTOLOGY_REVIEW.md ranked by severity. Checks view conventions, prompt/view alignment, top-comment quality, low-value columns via live column profiling, meta-information leakage, and (if present) derived-dimension recipes against their tasks/views/tools. Use after any material change to views, prompts, or derived dimensions, before demoing to a customer, or when the agent is giving shaky answers.
allowed-tools: Bash Read Write Edit Grep Glob
---

# Review ontology

Audit the coherence of an existing ontology. You are looking for **mismatches between use cases, views, and prompts**, plus anything that shouldn't reach the agent.

This skill is **read-only**. It produces a report. It does not edit views or prompts. The user decides what to act on.

If the sibling skill `build-ontology` is the constructor, this is the inspector.

## When NOT to use this skill

- The agent is fine; you just want to spot-check one view (read the view directly)
- You haven't changed anything since the last review and `ONTOLOGY_REVIEW.md` is recent (just re-read it)
- There's nothing to review — no views, no prompts (run `build-ontology` first)

## Prerequisite

This skill expects `data/datasets/views/*.sql` and at least one toolbox prompt to exist. If neither does, STOP and tell the user to run `build-ontology` first.

## Inputs

Read these as the source of truth (nothing else):

- `data/datasets/views/*.sql` — the agent-facing semantic layer
- `data/datasets/derived/*.recipe.md` — recipes for derived dimensions (if present; from `extend-ontology`)
- `data/datasets/derived/<name>/` — derived Delta tables produced by batch tasks
- `backend/core/tasks/*.py` and `backend/customer/tasks/__init__.py` — task implementations and registrations
- `backend/prompts/system.md` — shared persona
- `backend/prompts/{toolbox}.md` — toolbox-specific instructions
- `docs/ontology.md` — the rulebook
- `docs/ONTOLOGY_NOTES.md` — assumptions, scope decisions, use-case hints, scaffolded-dimension status
- `docs/INGEST_NOTES.md` — what was ingested, data-quality flags (if `ingest-data` ran)
- `backend/customer/queries.py` — dashboard queries (signals which views/columns matter)
- `backend/customer/tools/__init__.py` — which toolboxes use which tools (including semantic-search tools)
- Live DuckDB profiling via `scripts/warehouse_debug.py profile <view>` — used to assess column value

## The use-case gate (STOP condition)

The first thing you do: extract the stated use cases. Every downstream judgement depends on knowing what the agent is for.

Look for use cases in:
1. `backend/prompts/{toolbox}.md` under sections like "What users typically need", "Reasoning guidance", persona description
2. `docs/ONTOLOGY_NOTES.md` if it documents scope and decisions
3. Named queries in `backend/customer/queries.py` — each one is a concretely supported use case

If use cases are clear, list them up top in the report and proceed.

**If use cases are NOT clear** — prompts are generic, no notes file, no named queries — STOP and ask the user:

> "Before I can review this ontology meaningfully, I need to know what decisions the agent is meant to support. Can you list the top 3-5 user questions or workflows? Without this, I can only check syntax and conventions, not whether the ontology earns its shape."

Do not continue until use cases are confirmed. Syntax-only reviews are low-value and the user will push back.

## Procedure

### 0. Check for a prior review

Before anything else, look for `docs/ONTOLOGY_REVIEW.md`. If it exists, the review is (partly) an **audit of progress against it** rather than a cold-start scan.

Gate on staleness:

```bash
# Commits touching views or prompts since the review was last updated.
git log --since="$(git log -1 --format=%cI -- docs/ONTOLOGY_REVIEW.md)" \
  --oneline -- data/datasets/views backend/prompts docs/ontology.md docs/ONTOLOGY_NOTES.md
```

- **Zero commits** since the report → the prior review is current. Open it, enumerate its findings, and structure this run as a delta: which findings are fixed, which remain, which are newly introduced. The report header must cite the prior review's date and call out "N of M prior findings resolved".
- **Some commits** → the review is partially stale. Still use it as a starting rubric (findings are usually still valid), but do a full re-scan and note which prior findings were resolved incidentally vs. still open.
- **Many commits or report older than ~30 days** → treat as stale reference only. Do a full review, but scan the prior report's findings list as prior art so you don't re-discover the same issues with different wording.

When a prior review exists, for each of its findings, explicitly classify in the new report:

- **Resolved** — re-run the same check; if it now passes, mark resolved and do not re-list under findings
- **Still open** — re-list under the same severity with a note `(carried from <prior date>)`
- **Regressed** — was resolved at some point, now broken again; list under findings with a `(regression)` note

This makes review-over-review progress visible and prevents the report from looking like the ontology made no progress when it did.

If no prior review exists, proceed to step 1 as a cold review.

### 1. Extract and confirm use cases

Read prompts + notes + named queries. Write a bulleted list of the use cases you extracted, then **present the list to the user before proceeding** and ask:

> "I extracted these use cases from <sources>. Is this still the rubric to review against, or has it drifted?"

The documented use cases may themselves be stale on an ontology that has evolved without a prompt update. Wait for confirmation (or corrections) before walking the checklist — the whole review depends on having the right rubric.

Once confirmed, put the final list at the top of the report. This list is the rubric for every "does this earn its place" judgement below.

### 2. Run structural validators

```bash
uv run python scripts/check_ontology.py
uv run python scripts/check_views.py
uv run python scripts/check_customer_config.py
```

Any failure here is a **Blocker**. Capture the output verbatim in the report.

### 2.5. Schema overview

Before deep profiling, get the lay of the land:

```bash
uv run python scripts/warehouse_debug.py schema
```

Scan the output for gross structural issues before spending time on per-column profiling:

- **Views with 0 rows** — probably a broken filter or a scope mismatch. Flag as **Coherence** (agent will see an empty entity).
- **Views with wildly more columns than peers** — often means a raw column that should have been pruned made it through.
- **Views with suspiciously few columns** — may have over-pruned a genuinely useful column.
- **Raw `_raw_*` tables with no corresponding view** — if a raw table was ingested but never modeled, note it under "What was not reviewed" at the end of the report. (Out of scope to fix, but worth calling out.)

This is a 5-second scan before the slower axis-by-axis work.

### 3. Walk the checklist

Open [review-checklist.md](review-checklist.md) and work through each axis. For every finding, record:

- **Severity**: Blocker / Coherence / Convention / Suggestion
- **Location**: file path + line range (or view/column name)
- **What's wrong**: one sentence
- **Why it matters**: which use case or convention it violates
- **Suggested fix**: not code — describe the change

### 4. Live column profiling

For each view, run:

```bash
uv run python scripts/warehouse_debug.py profile <view>
```

For every column in the view's output, judge against the use cases:

- **0% NULL, referenced by a use case** → keep, no finding
- **High NULL rate (>70%), not referenced by any use case** → **Coherence** finding: low-value column
- **Near-unique cardinality** (e.g. an ID column) with no join target → **Coherence** finding: possible dangling ID
- **Low cardinality** (2-10 distinct values) but values are raw codes, not decoded → **Convention** finding: undecoded code
- **Name does not include a unit** where one is implied (amounts, durations, weights) → **Convention** finding

Record one finding per column issue. Do not flood the report with borderline cases — only raise when you can cite a use case or rule it fails.

### 5. Hunt meta-information

Grep for engineer-only concerns in agent-visible text (view top-comments and prompts). Flag as **Coherence**:

- References to `_raw_*` tables, ingestion process, Delta Lake, DuckDB internals
- References to ontology-building scripts (`check_views.py`, `warehouse_debug.py`, `generate_column_usage.py`)
- References to `ONTOLOGY_NOTES.md` or other internal docs
- Historical carve-out notes ("we previously had X, now Y")
- `TODO`, `FIXME`, "placeholder", "will be filled in", "not yet implemented"
- References to customer forking, template code, file layout
- Instructions aimed at Fulcrum engineers rather than at the agent

Useful greps:

```bash
grep -n -E "_raw_|ONTOLOGY_NOTES|check_views|TODO|FIXME|placeholder" \
  data/datasets/views/*.sql backend/prompts/*.md
```

Read context around each hit — some references are fine (e.g. `_raw_` inside a `FROM` clause is necessary), but any of these appearing inside a `-- description:` block or a prompt body is a finding.

### 6. Prompt ↔ view alignment

For each prompt file, cross-reference every noun it names:

- Does it reference view names the agent sees? Good.
- Does it reference column names? Do those columns still exist in the view?
- Does it describe pre-applied filters (scope gate, time window)? Do the views actually enforce them?
- Does it promise a column (e.g. "use `sourcing_type` to distinguish...") that is actually present?

A prompt that references a removed column is a **Coherence** finding (the agent gets a SQL error and recovers — not a hard break). A prompt that describes a filter the view no longer applies is also **Coherence**. Reserve **Blocker** for things that actually stop the agent from operating (view won't compile, config check fails).

### 7. Top-comment quality

For each view, read only the top `-- ...` block (what the agent sees). Check:

- Starts with `One row per <grain>.` — grain stated first
- States the use case in one sentence
- Names the joins (`Joins: foo_id -> other_view.foo_id`)
- States any pre-applied filters
- Does NOT contain meta-information (see step 5)
- Matches the current SQL below it — not stale

Missing grain is **Convention**. Stale description (claims X but SQL does Y) is **Coherence**.

### 8. Convention sweep

Walk [review-checklist.md](review-checklist.md) naming and structural checks. Most will be **Convention** severity. Batch them in the report — don't write a paragraph per missing underscore.

### 9. Agent test-drive

Static checks find disagreements on paper. The strongest coherence signal is watching the real agent answer a real question from the use-case list.

From the confirmed use cases, derive 3-5 sample questions phrased like a real user would ask. For each, POST to the chat endpoint and read the response.

```bash
# Prerequisite: backend running. Use the repo's start.sh — it brings up the
# database container, runs migrations, and starts the backend + frontend.
./start.sh &
```

The chat endpoint is unauthenticated at the API level (no API key, no session — just CORS), so a direct `curl` works. Pass the toolbox via the `X-Toolbox` header.

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Toolbox: sales' \
  -d '{"messages":[{"id":"t1","role":"user","parts":[{"type":"text","text":"Which customers had the largest drop in spend vs. prior year?"}]}]}'
```

The response is Vercel-AI-SDK streaming format; read it as-is (don't need to parse perfectly — you're looking for the tool calls and the final answer).

For each sample question, judge:

- **Did the agent pick the right view?** (Look at `execute_sql` tool calls.) Wrong view = **Coherence** finding against the view that should have been chosen (probably a weak top-comment description).
- **Did the SQL reference columns that exist?** Hallucinated columns = **Coherence** against whatever prompt or description misled the agent.
- **Did the agent apply scope filters correctly?** (E.g. not re-applying a 2024+ filter on a pre-filtered view.) Wrong filter = **Coherence** against the prompt not stating the pre-filter.
- **Was the answer useful or did the agent punt?** Frequent "I don't have enough information" on in-scope questions = **Coherence** against missing computed columns or missing JOINs.

Record findings tied to what you observed, not what you expected. Each test-drive finding must cite the exact question asked and the relevant tool calls or output.

If the backend isn't practical to start (environment constraints), skip this axis and note it under "What was not reviewed". Don't skip silently.

### 10. Write the report

Use [report-template.md](report-template.md) as the shape. Write to `docs/ONTOLOGY_REVIEW.md` (overwrite any existing file — this is a point-in-time snapshot; use git if you need history).

Rank findings by severity. Within each severity, group by view/prompt file. Keep items short: one bullet per finding with file:line and a one-sentence fix.

If a prior review existed (step 0), the summary must name it: "Prior review: <date>. N of M findings resolved. K new. J regressions." Also add a `## Resolved since <prior-date>` section listing resolved findings by title so the user can see forward progress without diffing two reports.

End with a one-paragraph summary of overall health and the top 3 things to fix first.

## Severity model

| Severity | Meaning | Examples |
|---|---|---|
| **Blocker** | Ontology is broken or contradicts itself | View won't compile; prompt references a column that doesn't exist; `check_customer_config.py` fails |
| **Coherence** | View, prompt, and use cases don't agree, OR meta-information reaches the agent | Prompt claims a filter the view doesn't apply; top-comment mentions ingestion internals; column with no use-case backing |
| **Convention** | Violates `view-conventions.md` but agent can probably still work | Missing unit in column name; raw code not decoded; missing type cast |
| **Suggestion** | Could be improved but not wrong | Could pre-compute a metric; could denormalize further |

Blockers must be listed first and must have explicit fix recommendations.

## What good looks like

- Every view column is traceable to a use case
- Every prompt claim is backed by a view
- Every top-comment states grain, use, joins, filters — and nothing else
- Zero meta-information in agent-visible text
- Conventions pass on a spot-check
- The report is short enough that the user will actually read it

## What to avoid

- Reviewing without knowing use cases — stop and ask
- Editing views or prompts — this skill is read-only, propose fixes in the report
- Flagging every minor thing — filter to real findings
- Rewriting the same finding for every view it affects — group by root cause
- Assuming the existing ontology is correct — it may be, but verify against the use cases
