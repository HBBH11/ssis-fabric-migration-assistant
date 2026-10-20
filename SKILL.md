---
name: ssis-fabric-migration-assistant
description: Assesses legacy SSIS (.dtsx) packages and SSAS tabular models (.bim/TMSL) for migration to Microsoft Fabric (Data Factory pipelines, Dataflow Gen2, notebooks, Fabric semantic models). Parses package XML to inventory control flow tasks, data flow components, connection managers, variables, and precedence logic, then classifies each package and component as auto-mappable vs. needing manual redesign with a Low/Medium/High risk rating. Produces per-package Markdown reports and a portfolio-level rollup with prioritized migration backlog. Use this whenever the user mentions SSIS-to-Fabric migration, asks "what does this .dtsx package do", wants an inventory or risk assessment of legacy SSIS/SSAS estate, needs to plan a Fabric migration for existing ETL, or uploads .dtsx/.bim/.asdatabase files for analysis — even if they only ask a narrow question about one package, since the full inventory/classification workflow is almost always more useful than a one-off answer.
---

# SSIS → Fabric Migration Assistant

Helps BI/data engineering teams stuck on legacy SSIS packages and SSAS
models understand what they have and plan a path to Microsoft Fabric. Sibling
skill to the TMDL Assistant — same author, same "don't guess, show your
work" philosophy: this skill classifies and drafts, it never pretends a
migration is finished.

## Hard rules (apply to every output this skill produces)

1. **Never claim a converted package is production-ready.** Every generated
   Fabric artifact (Phase 2) is labeled `DRAFT / NEEDS REVIEW` with an
   explicit list of what wasn't converted and why. This applies to Phase 1
   reports too: never round a "Partial" or risky component up to "fully
   auto-mappable."
2. **Degrade gracefully on bad input.** Real `.dtsx` files are often messy —
   malformed XML, missing sections, packages exported from mismatched SSIS
   versions. `scripts/parse_dtsx.py` already handles this (see its
   `parse_status` and `parse_warnings` fields) — never fail outright or
   fabricate structure the parser couldn't find. If `parse_status` is
   `"failed"` or `"partial"`, say so plainly in the report's Parse Notes
   section instead of writing around the gap.
3. **Offline by default.** Work only from the files provided. Never assume
   live Azure/Fabric API access. Where such access would materially improve
   accuracy (resolving a dynamic connection string, confirming a target
   Fabric capacity's supported connectors), name that explicitly in the
   report's "What Would Improve Accuracy" section rather than silently
   guessing.
4. **Never invent an SSIS→Fabric equivalence that isn't in
   `references/ssis-fabric-mapping.md`.** If a component or task type isn't
   covered there, say so and flag it for manual review rather than
   improvising a plausible-sounding mapping.

## Workflow

### Step 1 — Ingest

Run the bundled parser against whatever the user provided:

```bash
python3 scripts/parse_dtsx.py <path-to-file-or-directory> --out parsed.json
```

- Single `.dtsx` file → single package JSON object.
- Directory of `.dtsx` files → `{"packages": [...]}` with one entry per file.
- The script never raises on malformed input — check each package's
  `parse_status` (`complete` / `partial` / `failed`) and `parse_warnings`
  before writing the report. A `failed` package still gets a report; it
  just says "here's what we couldn't determine" instead of an inventory.
- The `signals` block in each parsed package (script task count, fuzzy
  lookup presence, nesting depth, dynamic connection strings, etc.) is
  precomputed specifically to drive Step 3's risk scoring — use it rather
  than re-deriving these counts by eye from the raw task list.

If the user hasn't provided any `.dtsx` files yet, ask for them (or a
directory/zip of them) before proceeding — this skill has nothing to
analyze without at least one package.

### Step 2 — Map components

For every task and data flow component in the parsed JSON, look up its
Fabric equivalent in `references/ssis-fabric-mapping.md` (§1 Control Flow,
§2 Data Flow, §3 Other Objects). Record, per component:
- The Fabric equivalent name
- Auto-mappable: Yes / Partial / No
- Any notes from the mapping table that apply (e.g., "Fuzzy Lookup has no
  direct equivalent")

Flag anything not found in the mapping table rather than guessing (Hard
rule 4).

### Step 3 — Score risk

Apply the heuristics in `references/ssis-fabric-mapping.md` §4 using the
package's `signals` block:
- Start at Low, escalate per the +1 tier / +2 tier rules
- A `parse_status` of `"failed"` automatically caps the package at High
  (per §4's "fails to parse cleanly" rule) — don't try to rate a package
  you couldn't actually read
- Write out *which* signals drove the rating — the report's "Risk Factors
  Identified" section should name specific components, not just say
  "scripting present"

### Step 4 — Write the report

Follow `references/report-template.md` exactly, per package:
1. Plain-language summary
2. Component inventory & mapping table
3. Connection managers
4. Variables & parameters
5. Precedence logic (plain language, not raw constraint IDs)
6. Risk factors identified
7. What wasn't converted / needs manual redesign — **mandatory even when
   the list is short**; never omit this section
8. Parse notes — state explicitly what didn't parse, if anything
9. What would improve accuracy

Save each report as Markdown (e.g. `<PackageName>_report.md`). Only
produce HTML in addition if the user asks for it.

When analyzing more than one package, also produce the **portfolio rollup**
(template in the same reference file): counts by risk tier, top blockers
ranked by how many packages they appear in, a separate list of deprecated
components found (CDC/Attunity, Data Profiling Task — these need
replacement regardless of risk tier), and a suggested migration order
(Low-risk/high-value first).

### Step 5 — Pause for feedback before Phase 2

Phase 1 (Steps 1–4) is the default scope. Do not draft Fabric pipeline
JSON, Dataflow Gen2/notebook skeletons, or a migration backlog project plan
unless the user has seen the Phase 1 report and explicitly asks to
continue — this mirrors the standard Inventory → Classify → Architect →
Convert → Validate → Cutover methodology, and Architect/Convert shouldn't
start before Classify is confirmed correct.

## Phase 2 (only after the user confirms Phase 1 output)

1. **Draft Fabric artifacts for Low/Medium risk packages only.** Produce
   either a first-pass Data Factory pipeline JSON definition or a Dataflow
   Gen2/notebook skeleton approximating the SSIS logic. Every such artifact
   must open with a `DRAFT / NEEDS REVIEW` banner (in a comment or a
   top-level `"_status"` field for JSON) listing what wasn't converted.
   Never attempt this for High-risk packages — the point of the risk
   rating is to say "this one needs a human to redesign it first."
2. **SSAS companion pass (optional, only if the user has .bim/TMSL/
   .asdatabase files).** Produce the same style of inventory + risk report
   for the tabular model side, then a draft TMDL file for the Fabric/Power
   BI semantic model target. Reuse conventions from the TMDL Assistant
   skill where they apply (e.g. its Generate/Validate mode conventions) so
   output style is consistent across both skills.
3. **Migration backlog generator.** Take the portfolio rollup and produce
   a phased, prioritized Markdown project plan following Inventory →
   Classify → Architect → Convert → Validate → Cutover, sequencing
   packages by risk tier and any Execute Package Task dependencies found
   between them.

## Trigger phrases

Fire this skill (even without an explicit "use the skill" ask) on things
like:
- "migrate this SSIS package to Fabric" / "SSIS to Fabric"
- "what does this .dtsx do"
- "can this be auto-converted" / "is this safe to convert"
- "assess our SSIS estate" / "inventory our SSIS packages"
- "how risky is this package to migrate"
- Any upload of one or more `.dtsx`, `.bim`, `.asdatabase`, or TMSL files
  with a question about migration, modernization, or "what's in this"
- "build a migration plan for our SSIS packages"

## Reference files

- `references/ssis-fabric-mapping.md` — the full SSIS→Fabric component
  equivalence table (control flow, data flow, other objects) and the
  risk-rating heuristics. Load this whenever mapping a component or
  scoring risk; don't improvise beyond it.
- `references/report-template.md` — exact per-package report shape and the
  portfolio rollup shape. Follow it structurally; don't freelance the
  section order.

## Bundled scripts

- `scripts/parse_dtsx.py` — stdlib-only XML parser for `.dtsx` files.
  Outputs structured JSON (tasks, data flow components, connection
  managers, variables, precedence constraints, plus a precomputed
  `signals` block for risk scoring). Handles malformed/partial files
  without crashing — always check `parse_status` before writing a report.
  No SSAS/.bim parser is bundled yet (Phase 2 item); until then, read
  `.bim`/TMSL files directly as JSON when that work starts.

## Assets

- `assets/sample_dtsx/Load_Sales_Staging.dtsx` — a synthetic sample package
  used to validate the parser (Execute SQL Task, Data Flow Task with 4
  components, a Script Task, and a Foreach Loop with a nested File System
  Task). Useful as a smoke test if the parser is modified later:
  `python3 scripts/parse_dtsx.py assets/sample_dtsx/Load_Sales_Staging.dtsx`
  should return `parse_status: "complete"` with 5 tasks and 4 data flow
  components.
