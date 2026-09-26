# Package: `Load_Sales_Staging.dtsx`

**Overall Risk Rating:** 🟡 Medium
**Auto-mappable:** Partially
**Parse status:** Complete

## 1. Plain-Language Summary

This package truncates a staging table, then loads sales transactions from
an OLTP source into staging through a data flow that converts data types
and adds a derived column. After loading, a C# script task validates row
counts, and a Foreach loop archives a file to a network share.

## 2. Component Inventory & Mapping

| # | Component | Type | Fabric Equivalent | Auto-mappable? | Risk Contribution |
|---|---|---|---|---|---|
| 1 | Truncate Staging Table | Execute SQL Task | Script Activity / Stored Procedure Activity | Yes | — |
| 2 | Load Sales Data Flow | Data Flow Task | Dataflow Gen2 | Partial | — |
| 2a | ↳ OLE DB Source | Data Flow Component | Dataflow Gen2 source | Yes | — |
| 2b | ↳ Data Conversion | Data Flow Component | Dataflow Gen2 "Change type" | Yes | — |
| 2c | ↳ Derived Column | Data Flow Component | Dataflow Gen2 custom column (M) | Yes, if expression is simple — not inspectable from XML alone | Low |
| 2d | ↳ OLE DB Destination | Data Flow Component | Dataflow Gen2 destination | Yes | — |
| 3 | Validate Row Counts | Script Task (C#) | Notebook Activity | No | Medium |
| 4 | Archive Loop | Foreach Loop Container | ForEach Activity | Yes (structurally) | — |
| 4a | ↳ Move File | File System Task | Copy Activity (move) | Yes | — |

## 3. Connection Managers

| Name | Type | Fabric Target | Notes |
|---|---|---|---|
| SALES_OLTP | OLE DB | Linked Service / Fabric connection to source SQL | Uses Integrated Security (SSPI) — confirm auth model, since Fabric connections typically use service principal or OAuth |
| STAGING_DW | OLE DB | Fabric Warehouse/Lakehouse connection | Same auth consideration as above |
| ARCHIVE_FLATFILE | Flat File | OneLake Files connection | Static UNC path; not dynamic |

## 4. Variables & Parameters

| Name | Scope | Type Code | Fabric Equivalent | Notes |
|---|---|---|---|---|
| BatchDate | Package | 7 (DateTime) | Pipeline parameter | |
| SourceRowCount | Package | 3 (Int32) | Pipeline variable | Written to by the Script Task — needs a Fabric-native way to persist (e.g. notebook output variable or a Lookup activity) |
| ArchiveFolder | Package | 8 (String) | Pipeline parameter | Hardcoded UNC path (`\\fileserver\archive\sales`) — confirm the OneLake path equivalent before conversion |

## 5. Precedence Logic

Straight-line, success-only flow: Truncate Staging Table → Load Sales Data
Flow → Validate Row Counts → Archive Loop. No conditional branches or
expression-based constraints were found — all three constraints use the
default "Success" value, so this maps cleanly to Fabric's default
`Success` dependency condition between activities.

## 6. Risk Factors Identified

- **+1 tier (Low → Medium):** One Script Task present (`Validate Row
  Counts`, C#) — per `ssis-fabric-mapping.md` §4, 1–2 Script Tasks push a
  package to Medium.
- No Fuzzy Lookup/Grouping, no CDC/deprecated components, no SCD Wizard,
  no dynamic connection strings, nesting depth is only 1 level (Archive
  Loop → Move File) — none of these High-risk factors are present, so the
  package stays at Medium rather than escalating further.

## 7. What Wasn't Converted / Needs Manual Redesign

- **`Validate Row Counts`** (Script Task, C#) — no Fabric-native
  equivalent. Logic must be re-implemented in a Notebook Activity
  (PySpark or Python). The script's actual validation logic could not be
  extracted from the `.dtsx` XML (SSIS stores compiled/project-level
  script code outside the task's inline XML) — a reviewer needs to open
  the package in SSDT to see what the C# code actually checks before
  rewriting it.
- **`Derived Column` expression** — the specific expression logic inside
  this component could not be resolved from the parsed structure (this
  parser extracts component presence and type, not per-column expression
  text). Confirm the expression is simple enough for a direct Power Query
  `M` translation, or flag it for manual redesign if it's not.

## 8. Parse Notes

Parsing was complete — no XML errors or missing sections. `parse_status:
"complete"`, no `parse_warnings` were raised. Note that this parser
intentionally does not extract Derived Column expression text or Script
Task source code (both require deeper, component-specific XML/VSA-project
parsing not in Phase 1 scope) — these are called out above as manual
follow-ups rather than treated as parse failures.

## 9. What Would Improve Accuracy

- Live access to the source SSIS Catalog (or the package's associated
  `.dtsProj` / script project files) would allow extracting the actual C#
  logic inside `Validate Row Counts` and the exact Derived Column
  expression, rather than only knowing they exist.
- Confirming the target Fabric workspace's supported authentication
  methods would resolve whether the OLE DB connections' Integrated
  Security setting has a direct equivalent or needs to change to a
  service principal.
