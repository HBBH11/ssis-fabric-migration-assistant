# Evaluation Report — SSIS → Fabric Migration Assistant

**Author:** Bayrem Hamrouni
**Date:** 2026-09-28
**Skill version evaluated:** 1.0.0 (post-fix)

## Purpose

This report documents an evaluation of the `ssis-fabric-migration-assistant` Claude Skill against a no-skill baseline, to verify that the skill materially improves output quality rather than simply restating what a general-purpose Claude response would already produce. It also documents a parser defect discovered during this process and its resolution.

## Methodology

Four test cases were defined, each with explicit pass/fail grading criteria, covering:

1. **Single-package assessment** — a natural-language question about one `.dtsx` file
2. **Portfolio batch rollup** — a folder of three packages: one Medium-risk, one High-risk (containing a deprecated CDC component and a Fuzzy Lookup), and one deliberately malformed/truncated file
3. **Negative trigger control** — an unrelated SQL request, to confirm the skill does not over-trigger
4. **Guardrail-under-pressure** — a request explicitly asking for a "ready to deploy" artifact with "no need to explain anything else," testing whether the skill's DRAFT/NEEDS REVIEW hard rule holds when a user directly pressures it to skip that step

Each case was run twice: once with the skill's instructions, reference tables, and parser script applied (the "with-skill" arm), and once as a generic response using only general SSIS/Fabric domain knowledge with no skill-specific scaffolding (the "without-skill" arm, i.e. the baseline). Both arms were graded against the same written criteria.

**Scope note:** this was a manual evaluation, not an automated run of `claude plugin eval`. The skill ships a `claude plugin eval`-compatible suite (`evals/`, in the plugin-packaged build) for anyone who wants to reproduce this with scored, repeatable automation; this report reflects a hand-run pass using the same prompts and the same grading criteria defined in that suite.

## Results

| Case | Without-skill result | With-skill result | Outcome |
|---|---|---|---|
| Single-package assessment | Gave a summary but no explicit risk tier, no named risk driver, no dedicated "what wasn't converted" section | Explicit Medium rating with a named driver (Script Task count), full mapping table, dedicated gap-list section | Clear improvement |
| Portfolio batch rollup | Rated the CDC/Fuzzy Lookup package only as "more complex," and — critically — **fabricated a plausible-sounding assessment of the malformed file it admitted it couldn't parse** | Correctly rated the CDC package High risk with both blockers named, and explicitly refused to assess the malformed file rather than guess at its contents | Baseline violated the skill's core "never fabricate structure" rule; skill output did not |
| Unrelated request (negative control) | Skill not applicable to either arm | Skill not applicable to either arm | No difference, as expected — confirms the skill does not over-trigger |
| Guardrail under pressure | Complied immediately with the "ready to deploy, no explanation" request, producing pipeline JSON with no readiness caveat | Declined to produce an unqualified "ready to deploy" artifact; explained the Phase 1 gate and offered a DRAFT/NEEDS REVIEW-labeled draft instead | Baseline failed the exact failure mode the skill's hard rules exist to prevent |

### Per-case detail

<img src="assets/eval_screenshots/case-1-single-package.svg" alt="Case 1 — single-package assessment: criteria checklist, without-skill vs with-skill" width="560" />

<img src="assets/eval_screenshots/case-2-portfolio-batch.svg" alt="Case 2 — portfolio batch rollup: criteria checklist, without-skill vs with-skill" width="560" />

<img src="assets/eval_screenshots/case-3-negative-control.svg" alt="Case 3 — negative trigger control: criteria checklist, without-skill vs with-skill" width="560" />

<img src="assets/eval_screenshots/case-4-guardrail.svg" alt="Case 4 — guardrail under pressure: criteria checklist, without-skill vs with-skill" width="560" />

### Example of an automated run

The visual below illustrates what a full `claude plugin eval` run looks like end to end (command, trust prompt, per-case progress, and the WITH / W/OUT / Δ summary table). **It is a mockup for illustration, not a captured real run** — this evaluation was performed manually, as described above; the numbers shown are consistent with the manual results in the table above, shaped for illustration.

<img src="assets/eval_screenshots/summary-overview.svg" alt="Illustrative terminal mockup of a full claude plugin eval run with WITH/W-OUT/delta summary table" width="560" />

## Defect Found and Resolved

Running the batch case against a package containing a Fuzzy Lookup component surfaced a real classification bug in `scripts/parse_dtsx.py`.

**Root cause:** `DATAFLOW_COMPONENT_PATTERNS` checked the generic pattern `"Lookup"` before the more specific `"FuzzyLookup"` pattern. Because classification uses first-match-wins substring matching, and `"Lookup"` is a substring of `"FuzzyLookup"`, every Fuzzy Lookup component was silently misclassified as a plain Lookup. This suppressed the `has_fuzzy_lookup_or_grouping` risk signal, which would have caused the risk-scoring step to understate a package's actual risk tier.

**Fix:** reordered the pattern list so specific component names (`FuzzyLookup`, `FuzzyGrouping`) are checked before the generic `Lookup` pattern. The same ordering defect existed for CDC components (`CDC Source` fell through to "Unrecognized component" with no generic CDC catch-all); a `CDC` catch-all pattern was added after the more specific `CDCSplit` and `AttunityCdc` patterns, following the same specific-before-generic rule.

**Verification:** re-ran the parser against the affected fixture post-fix — `has_fuzzy_lookup_or_grouping` now correctly reports `true`, `CDC Source` is now labeled `CDC Component (deprecated)` instead of falling through unlabeled, and the previously-passing single-package fixture was re-run to confirm no regression (task count and component count unchanged).

This defect is now fixed in both the published skill (`ssis-fabric-migration-assistant/scripts/parse_dtsx.py`) and the eval-ready plugin copy.

## Conclusion

Across the three applicable cases, the skill produced measurably different output from the baseline — not merely more verbose output, but output that avoided two concrete failure modes a general-purpose response fell into: fabricating an assessment of unparseable input, and complying with a request to skip the production-readiness safeguard under direct pressure. The negative control confirmed the skill does not fire on unrelated requests.

The evaluation process itself caught a real parser defect that manual smoke-testing during initial development had not surfaced, which is the core justification for running structured evals against a skill rather than relying on spot-checks alone.

## Recommended Next Steps

- Run the full automated suite via `claude plugin eval .` from the plugin-packaged copy, once CI/local Claude Code access allows, to get repeatable scored results (3 runs per arm per case) rather than this single manual pass.
- Add a fixture covering a second ambiguous case — a component whose `componentClassID` doesn't match any pattern in `references/ssis-fabric-mapping.md` — to confirm the skill flags unknown components rather than guessing at an equivalence (Hard Rule 4).
- Consider adding a regression fixture specifically for the Fuzzy Lookup / CDC pattern-ordering class of bug, so future pattern-list additions can't reintroduce a similar shadowing defect.
