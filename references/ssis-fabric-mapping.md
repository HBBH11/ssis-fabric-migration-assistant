# SSIS → Microsoft Fabric Component Mapping & Risk Heuristics

Load this file when classifying components or scoring package risk. It is the
authoritative mapping table — don't improvise equivalences that aren't listed
here without flagging them as unverified.

## 1. Control Flow Task Mapping

| SSIS Task | Fabric Equivalent | Auto-mappable? | Notes |
|---|---|---|---|
| Execute SQL Task | Script Activity (Fabric DW/Lakehouse) or Stored Procedure Activity | Yes, if target is Fabric DW/Warehouse and SQL is ANSI-standard | T-SQL-specific syntax (e.g. `OPENROWSET`, linked servers) needs rewrite |
| Data Flow Task | Dataflow Gen2, or Copy Activity (for simple extract-load) | Partial — depends on components inside (see §2) | Copy Activity only covers source→dest with light mapping; anything transformational goes to Dataflow Gen2 or a notebook |
| Script Task (VB.NET/C#) | Notebook Activity (PySpark/Python) | No — needs manual rewrite | Logic must be re-authored; .NET libraries referenced inside have no direct Spark equivalent |
| Script Component (in Data Flow) | Notebook transformation cell | No | Same as above, at the row/column transform level |
| For Loop Container | ForEach Activity (with `Until` condition) or a pipeline `Until` activity | Yes, structurally | Loop expression syntax must be translated to pipeline expression language |
| Foreach Loop Container | ForEach Activity | Yes, for File/Item enumerators. No, for ADO/ADO.NET recordset or Variable enumerators | Enumerator type changes the mapping — flag ambiguous cases |
| Sequence Container | Pipeline "Activities" grouping (no direct 1:1 — flatten into ordered/parallel activities) | Yes, structurally | Fabric pipelines have no visual container; document intent in activity naming/description instead |
| Send Mail Task | Office 365 Outlook connector activity, or Web Activity + Logic App | Partial | Requires a connection to an email service; not a native pipeline activity |
| File System Task | Copy Activity (for file moves/copies) or a notebook using `mssparkutils.fs` | Yes for simple copy/move/delete | Complex file system operations (e.g. wildcard rename batches) need a notebook |
| FTP Task | Copy Activity with FTP/SFTP linked service | Yes | Confirm Fabric supports the specific FTP variant (FTP vs SFTP vs FTPS) |
| Execute Package Task | Invoke Pipeline activity | Yes | Parent/child package parameter passing maps to pipeline parameters |
| Execute Process Task | No native Fabric equivalent | No | Typically requires re-architecting as a notebook call or external Azure Function/Web Activity |
| Data Profiling Task | No native Fabric equivalent | No | Recommend Fabric's built-in data quality / profiling in Lakehouse instead of migrating this task literally |
| WMI Event Watcher Task | No native Fabric equivalent | No | Re-architect using Fabric's event-based triggers (Fabric event streams / Data Activator) |
| Analysis Services Processing Task | Semantic model refresh (via Fabric REST API / Power BI refresh) | Partial | Not a pipeline-native activity; typically a Web Activity calling the refresh API |
| Transfer/Bulk Insert Task | Copy Activity | Yes | Bulk Insert's file-format quirks (fixed-width, custom delimiters) need explicit mapping |

## 2. Data Flow Component Mapping

| SSIS Data Flow Component | Fabric Equivalent | Auto-mappable? | Notes |
|---|---|---|---|
| OLE DB / ADO.NET Source | Dataflow Gen2 source / Copy Activity source | Yes | Connection manager becomes a Fabric connection/linked service |
| Flat File Source | Dataflow Gen2 source (Text/CSV) | Yes | Watch for custom row/column delimiters and header row quirks |
| Excel Source | Dataflow Gen2 source (Excel connector) | Yes | Named ranges / non-standard sheets need manual check |
| Data Conversion | Dataflow Gen2 "Change type" step | Yes | |
| Derived Column | Dataflow Gen2 "Custom column" (Power Query M) | Yes, for simple expressions. No, for complex nested SSIS expression language | SSIS expression syntax ≠ M syntax; nontrivial expressions need manual translation |
| Conditional Split | Dataflow Gen2 "Split column" / multiple filtered queries | Partial | Multi-branch splits with overlapping conditions need redesign as separate queries |
| Lookup | Dataflow Gen2 "Merge queries" | Yes, for exact-match lookups. No, for fuzzy/partial-cache lookups | Fuzzy Lookup has no direct Fabric equivalent — flag as High risk |
| Fuzzy Lookup / Fuzzy Grouping | No native Fabric equivalent | No | Consider a notebook using a fuzzy-matching Python library, or Azure AI Search |
| Merge / Merge Join | Dataflow Gen2 "Merge queries" / "Append queries" | Yes | Requires sorted inputs in SSIS; Fabric merge does not have this constraint, note as a simplification |
| Aggregate | Dataflow Gen2 "Group by" | Yes | |
| Sort | Dataflow Gen2 "Sort" | Yes | |
| Multicast | Reused query referenced by multiple downstream steps | Yes, structurally | Not a literal component — represented as query fan-out |
| Slowly Changing Dimension (SCD) Wizard | No native Fabric equivalent | No | This is the highest-friction component to migrate — recommend a notebook implementing SCD Type 1/2 logic explicitly |
| CDC Source/Splitter (Attunity/Microsoft CDC) | Deprecated — replace with Fabric mirroring or a notebook-based CDC pattern | No | Flag any package using this as High risk regardless of other complexity |
| OLE DB / ADO.NET Destination | Dataflow Gen2 destination / Copy Activity sink | Yes | |
| Script Component (Source/Transform/Destination) | Notebook cell (PySpark) | No | Always flag for manual rewrite |
| Row Count | Pipeline "Get row count" via Lookup/Script activity, or notebook variable | Partial | Often used for auditing — semantics should be preserved even if mechanism differs |

## 3. Other Objects

| SSIS Object | Fabric Equivalent | Notes |
|---|---|---|
| Connection Manager (OLE DB/ADO.NET, SQL) | Fabric Linked Service / Connection | Map connection string components (server, database, auth) to the new connection's parameters |
| Connection Manager (Flat File) | Fabric connection to Lakehouse Files / OneLake | |
| Package Variable | Pipeline Parameter or Variable | Scope carefully: SSIS package-level vs. task-level variables often collapse into pipeline parameters |
| Package Configuration (XML/SQL config) | Fabric pipeline parameters + Azure Key Vault-backed connections | Externalized configs need a deliberate secrets-management decision |
| Event Handlers (OnError, OnPreExecute, etc.) | Pipeline activity dependency conditions (`Failure`, `Success`, `Completion`) + Fabric Data Activator for alerting | Not 1:1 — event handler logic must be redistributed across activity-level conditions |
| Checkpoints/Restartability | Pipeline "rerun from failed activity" | Native pipeline rerun covers most checkpoint use cases |

## 4. Risk Rating Heuristics

Score each package, then bucket it. These are heuristics, not a certified
scoring standard — recalibrate them against a handful of your own packages
before trusting the output at scale.

**Start at Low. Escalate based on what's present:**

- **+1 tier (Low→Medium) if any of:**
  - 1–2 Script Tasks or Script Components present
  - More than 5 Data Flow components in a single pipeline
  - Any Fuzzy Lookup/Fuzzy Grouping usage
  - Package Configurations referencing external XML/SQL config
  - More than 3 levels of nested containers (Sequence/For/Foreach)

- **+2 tiers (straight to High), or push Medium→High if already elevated:**
  - Any CDC/Attunity component (deprecated technology — always flag)
  - SCD Wizard component present
  - 3+ Script Tasks/Components, or any Script Task with >50 lines of code (if inspectable)
  - Execute Process Task or WMI Event Watcher Task present (no Fabric equivalent)
  - Dynamic/expression-driven connection strings (can't resolve without live environment access)
  - Custom .NET assemblies referenced by a Script Task/Component
  - Event handlers with non-trivial logic (not just a log-and-continue pattern)

- **Cap at High regardless of other factors if:**
  - The package fails to parse cleanly (malformed XML, missing expected sections) — until a human confirms what's actually inside, treat unknown as worst-case

**Rough tier definitions:**
- **Low** — Standard source→transform→destination flow, common connection managers, no scripting, mapped 1:1 using this table. Good auto-conversion candidate.
- **Medium** — Some manual redesign needed (a Script Task, a moderately complex expression, an unusual enumerator) but the overall shape of the package is still auto-mappable.
- **High** — Contains at least one component with no direct Fabric equivalent, deprecated tech (CDC/Attunity), or enough scripting/expression logic that a rewrite — not a conversion — is the realistic path.

## 5. Portfolio Rollup Guidance

When summarizing across packages:
- Count packages per risk tier.
- Rank "top blockers" by how many packages they appear in (e.g., "Fuzzy Lookup appears in 12/40 packages" is a bigger structural issue than a one-off Execute Process Task).
- Call out any deprecated component (CDC/Attunity, Data Profiling Task) separately from the risk tiers, since these need replacement regardless of conversion effort — they're an "end of life" list, not just a difficulty rating.
