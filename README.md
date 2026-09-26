# SSIS → Fabric Migration Assistant

A [Claude Skill](https://www.anthropic.com/news/skills) that assesses legacy SSIS (`.dtsx`) packages and SSAS tabular models for migration to Microsoft Fabric — turning an undocumented pile of packages into a scored, prioritized migration plan.

Sibling project to [TMDL Assistant](#) — same author, same philosophy: classify and draft, never claim a migration is finished until a human has reviewed it.

---

## The problem this solves

Most BI teams sitting on legacy SSIS have dozens to hundreds of undocumented `.dtsx` packages and no clear picture of:

- What each package actually does
- Which components map cleanly to Fabric (Data Factory pipelines, Dataflow Gen2, notebooks) and which don't
- Which packages are safe to auto-convert vs. which need a full rewrite
- Where to even start

This skill answers those questions from the package files themselves — no live Azure/Fabric access required — and produces a report a migration lead can actually hand to stakeholders.

## What it does (Phase 1)

Given one or more `.dtsx` files, the skill:

1. **Parses** the package XML to extract control flow tasks, data flow components, connection managers, variables/parameters, and precedence logic
2. **Maps** every component against a standard SSIS → Fabric equivalence table (Data Flow Task → Dataflow Gen2, Script Task → Notebook Activity, Execute SQL Task → Script/Stored Procedure Activity, etc.)
3. **Scores risk** per package (Low / Medium / High) based on heuristics — Script Task usage, deprecated CDC/Attunity components, Fuzzy Lookup, custom .NET, nesting depth, dynamic connection strings
4. **Flags** every component as auto-mappable or needs-manual-redesign — at the component level, not just the package level
5. **Reports** — a Markdown report per package, plus a portfolio-level rollup: risk tier counts, top blockers ranked by how many packages they affect, deprecated components found, and a suggested migration order

## What it deliberately does NOT do (yet)

Phase 2 — draft Fabric pipeline JSON / Dataflow Gen2 skeletons for Low/Medium risk packages, an SSAS/TMDL companion pass, and a full migration backlog generator — is designed but intentionally gated behind human review of the Phase 1 output. The skill will not attempt Phase 2 work until you've validated the Phase 1 classification against your own packages. See [Roadmap](#roadmap).

**Hard constraint that applies throughout:** no output from this skill ever claims a converted package is production-ready. Every draft artifact is explicitly labeled `DRAFT / NEEDS REVIEW` with what wasn't converted and why.

## How it works

This is a [Claude Skill](https://www.anthropic.com/news/skills) — a folder of instructions, reference data, and a bundled script that Claude loads on demand rather than a standalone application.

```
ssis-fabric-migration-assistant/
├── SKILL.md                          # Workflow, hard rules, trigger phrases
├── references/
│   ├── ssis-fabric-mapping.md        # Full SSIS→Fabric component equivalence table + risk heuristics
│   └── report-template.md            # Exact per-package report shape + portfolio rollup shape
├── scripts/
│   └── parse_dtsx.py                 # Stdlib-only XML parser — no dependencies, runs fully offline
└── assets/
    └── sample_dtsx/
        ├── Load_Sales_Staging.dtsx           # Synthetic test package
        └── Load_Sales_Staging_report.md      # Example output generated from it
```

The heavy lifting — the actual XML parsing — is deterministic Python, not an LLM guessing at structure. Claude reads the parser's JSON output and applies the judgment calls (risk scoring, plain-language summaries, what needs manual review) on top of it.

## Installation

**In Claude.ai / Claude Code / Claude Desktop:**

1. Download or clone this repository
2. Add the `ssis-fabric-migration-assistant/` folder to your Skills directory (or use the "Save skill" option if you received it as a `.skill` file)

**Standalone (just the parser):**

The parser has zero external dependencies — only the Python standard library:

```bash
python3 scripts/parse_dtsx.py path/to/package.dtsx
```

## Usage

Once the skill is available, just talk to Claude naturally:

> "What does this SSIS package do?" *(with a `.dtsx` attached)*

> "Assess our SSIS estate for a Fabric migration" *(with a folder of packages)*

> "Is this package safe to auto-convert?"

Claude will parse the file(s), classify each component, score the risk, and return a full inventory report — no need to invoke the parser script yourself, though you can run it directly if you just want the raw structured JSON.

### Running the parser directly

```bash
# Single package
python3 scripts/parse_dtsx.py MyPackage.dtsx

# Batch — every .dtsx in a directory
python3 scripts/parse_dtsx.py ./packages/ --out portfolio.json
```

Output is JSON: parsed tasks, data flow components, connection managers, variables, precedence constraints, and a precomputed `signals` block (script task count, fuzzy lookup presence, nesting depth, etc.) used to drive risk scoring.

The parser never fails outright on malformed input — a corrupt or partial `.dtsx` file still returns a result, with `parse_status: "failed"` or `"partial"` and a human-readable explanation in `parse_warnings`, rather than crashing the whole run.

### Example output

See [`assets/sample_dtsx/Load_Sales_Staging_report.md`](assets/sample_dtsx/Load_Sales_Staging_report.md) for a full sample report, generated end-to-end against the included synthetic test package — an Execute SQL Task, a 4-component data flow, a Script Task, and a nested Foreach Loop, rated Medium risk.

## Risk rating methodology

Full heuristics live in [`references/ssis-fabric-mapping.md`](references/ssis-fabric-mapping.md#4-risk-rating-heuristics). Summary:

| Tier | Meaning |
|---|---|
| 🟢 **Low** | Standard source→transform→destination flow, common connection managers, no scripting. Good auto-conversion candidate. |
| 🟡 **Medium** | Some manual redesign needed (a Script Task, a moderately complex expression) but the overall shape is still auto-mappable. |
| 🔴 **High** | Contains a component with no direct Fabric equivalent (Fuzzy Lookup, SCD Wizard, CDC/Attunity), or enough scripting that a rewrite — not a conversion — is the realistic path. |

These are heuristics, not a certified scoring standard — recalibrate against a handful of your own packages before trusting the output at scale.

## Roadmap

- [x] **Phase 1** — Parse, classify, score, report (this release)
- [ ] **Phase 2** — Draft Fabric pipeline JSON / Dataflow Gen2 skeletons for Low/Medium risk packages (always labeled `DRAFT / NEEDS REVIEW`)
- [ ] **Phase 2** — SSAS tabular model companion pass (`.bim`/TMSL parsing) with draft TMDL output, reusing conventions from [TMDL Assistant](#)
- [ ] **Phase 2** — Migration backlog generator: phased project plan (Inventory → Classify → Architect → Convert → Validate → Cutover) sequenced by risk tier and package dependencies

## Limitations

- Offline by design — does not connect to a live SSIS Catalog or Azure/Fabric APIs. Anything that would require live access (resolving a dynamic connection string, confirming a target capacity's supported connectors) is flagged in each report rather than guessed.
- The parser extracts component *presence and type*, not the contents of Derived Column expressions or compiled Script Task source code — these are always flagged for manual review rather than silently skipped.
- Risk heuristics are a starting point, not a certified migration methodology. Validate against your own package portfolio.

## Contributing

Issues and PRs welcome — particularly real-world `.dtsx` edge cases (SSIS version quirks, uncommon task types) that the parser or mapping table don't yet handle correctly.

## Author

Built by [Bayrem Hamrouni](https://github.com/HBBH11) — BI Engineer & Data Analyst specializing in Power BI, DAX, SQL, and Microsoft Fabric.

## License

MIT — see [LICENSE](LICENSE).
