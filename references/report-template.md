# Package Inventory & Classification Report Template

Use this shape for every per-package report. Fill in each section from the
parsed output of `scripts/parse_dtsx.py`; don't skip the "Not Converted"
section even for Low-risk packages — state "None" explicitly rather than
omitting it.

---

# Package: `<PackageName>.dtsx`

**Overall Risk Rating:** 🟢 Low / 🟡 Medium / 🔴 High
**Auto-mappable:** Yes / Partially / No
**Parse status:** Complete / Partial (see Parse Notes below)

## 1. Plain-Language Summary

*2–4 sentences, no jargon. What does this package actually do, end to end?
Example:*

> This package truncates a staging table, loads sales transactions from the
> OLTP source into staging via a data flow with type conversion and a
> derived column, runs a C# script to validate row counts, then archives
> processed files to a network share in a loop.

## 2. Component Inventory & Mapping

| # | Component | Type | Fabric Equivalent | Auto-mappable? | Risk Contribution |
|---|---|---|---|---|---|
| 1 | Truncate Staging Table | Execute SQL Task | Script Activity / Stored Procedure Activity | Yes | — |
| 2 | Load Sales Data Flow | Data Flow Task | Dataflow Gen2 | Partial (see sub-components) | — |
| 2a | ↳ OLE DB Source | Data Flow Component | Dataflow Gen2 source | Yes | — |
| 2b | ↳ Data Conversion | Data Flow Component | Dataflow Gen2 "Change type" | Yes | — |
| 2c | ↳ Derived Column | Data Flow Component | Dataflow Gen2 custom column (M) | Yes, if expression is simple | Low |
| 2d | ↳ OLE DB Destination | Data Flow Component | Dataflow Gen2 destination | Yes | — |
| 3 | Validate Row Counts | Script Task (C#) | Notebook Activity | No | Medium–High |
| 4 | Archive Loop | Foreach Loop Container | ForEach Activity | Yes (structurally) | — |
| 4a | ↳ Move File | File System Task | Copy Activity (move) | Yes | — |

*(Row count and exact structure will vary per package — this is illustrative.)*

## 3. Connection Managers

| Name | Type | Fabric Target | Notes |
|---|---|---|---|
| SALES_OLTP | OLE DB | Linked Service / Fabric connection to source SQL | Confirm auth model (SSPI won't carry over as-is) |
| STAGING_DW | OLE DB | Fabric Warehouse/Lakehouse connection | |
| ARCHIVE_FLATFILE | Flat File | OneLake Files connection | |

## 4. Variables & Parameters

| Name | Scope | Type | Fabric Equivalent | Notes |
|---|---|---|---|---|
| BatchDate | Package | DateTime | Pipeline parameter | |
| SourceRowCount | Package | Int32 | Pipeline variable | Written to by Script Task — needs a Fabric-native way to persist (e.g. notebook output or a lookup) |
| ArchiveFolder | Package | String | Pipeline parameter | Hardcoded UNC path — confirm OneLake path equivalent |

## 5. Precedence Logic

Describe the control flow order and any conditional branches
(Success/Failure/Completion) in plain language. Flag anything relying on
expression-based precedence constraints — these need explicit translation
to Fabric pipeline activity dependency conditions.

## 6. Risk Factors Identified

- List each factor that drove the risk rating, referencing
  `references/ssis-fabric-mapping.md` §4 (e.g., "Contains 1 Script Task →
  +1 tier").
- Be specific: name the component, not just "scripting present."

## 7. What Wasn't Converted / Needs Manual Redesign

**This section is mandatory even for Low-risk packages.** List every
component or piece of logic flagged as not auto-mappable, and why:

- `Validate Row Counts` (Script Task, C#) — no Fabric-native equivalent;
  logic must be re-implemented in a Notebook Activity (PySpark or Python).
  Reviewer should confirm what the validation logic actually checks before
  rewriting.
- *(add every such item — never leave this list implicitly empty)*

## 8. Parse Notes

State what was and wasn't successfully parsed from the raw `.dtsx` XML.
If the file was malformed or partially unreadable, say so here explicitly
rather than silently omitting affected sections — e.g.:

> Expression contents inside the Derived Column component could not be
> fully resolved from the XML; manual inspection in SSDT is recommended for
> exact logic.

## 9. What Would Improve Accuracy

Call out anything that live access (Azure/Fabric APIs, a running SSIS
Catalog, source database schema) would resolve — e.g., dynamic connection
strings, external package configurations, or schema-dependent expressions.

---

# Portfolio Rollup Template (use once per batch of packages)

## Summary

- **Packages analyzed:** N
- **🟢 Low risk:** N (N%)
- **🟡 Medium risk:** N (N%)
- **🔴 High risk:** N (N%)
- **Packages that failed to fully parse:** N

## Top Blockers Across the Portfolio

Rank by how many packages each blocker appears in, not by severity alone:

| Blocker | Packages Affected | Fabric Path Forward |
|---|---|---|
| Fuzzy Lookup / Fuzzy Grouping | N/Total | No direct equivalent — notebook w/ fuzzy-match library |
| CDC/Attunity components (deprecated) | N/Total | Replace with Fabric mirroring or notebook CDC pattern |
| Script Task / Script Component | N/Total | Rewrite as Notebook Activity (case-by-case) |

## Deprecated Components Found (Flag Separately From Risk Tiers)

List packages containing CDC/Attunity, Data Profiling Task, or other
deprecated SSIS technology — these need replacement regardless of
conversion effort.

## Suggested Migration Order

Recommend starting with Low-risk, high-value packages to build momentum and
validate the toolchain before tackling High-risk packages. Note any
dependencies between packages (e.g., Execute Package Task chains) that
constrain ordering.
