# Verification evidence

These results concern the bounded retained workbooks, not arbitrary XLSX correctness or financial accuracy. All source files remained byte-identical after inspection and browser testing.

## Independent spreadsheet comparison

`results/libreoffice.json` records a fresh run of **LibreOffice 24.2.7.2 420(Build:2)**. `scripts/verify_libreoffice.py` opens each public workbook hidden/read-only, with macro execution and link updates disabled. It extracts reference structures using Calc's `XFormulaTokens.getTokens()`. Coordinate expansion and sheet handling are implemented separately from the application's openpyxl tokenizer. The application supplies the cells/edges being checked, but not the oracle reference extraction.

| Workbook | Supported formulas | Partial formulas checked | Unique extracted edges checked | Token mismatches |
|---|---:|---:|---:|---:|
| CashFlowCompany.xlsx | 4 | 0 | 24 | 0 |
| Loan.xlsx | 96 | 0 | 384 | 0 |
| Valuation.xlsx | 1,026 | 41 | 2,546 | 0 |
| Total | 1,126 | 41 | 2,954 | 0 |

For supported formulas, the extracted target set must equal Calc's reference-token set. For partial formulas, every extracted target must occur in Calc's set; unextracted references can remain unresolved. The 55 unsupported valuation formulas have no extracted edges and are not counted as verified. Repeated reference tokens can produce multiple evidence rows for the same target; the application has 2,973 evidence rows, but only 2,954 unique formula-target edges.

### Negative result: precedent-query limitations

The script also compares `XFormulaQuery.queryPrecedents(False)` for all checked formula cells and retains every discrepancy. There are **40 query mismatches**, all in Valuation.xlsx:

- Ten fully supported cross-sheet formulas return precedent coordinates on the formula's own sheet. For example, Valuation!H57 explicitly references `'Financial Model'!$D$263`; Calc's query returned Valuation!D263, while Calc's token structure and the source XML both identify Financial Model!D263. This behavior is consistent with [LibreOffice bug 159973](https://bugs.documentfoundation.org/show_bug.cgi?id=159973); the upstream bug page was access-blocked in this environment, while its [public bug-notification archive](https://www.mail-archive.com/libreoffice-bugs%40lists.freedesktop.org/msg1009242.html) was discoverable. The observed mismatch is reproduced locally, not assumed solely from that report.
- Thirty partial formulas containing broken references return no valid precedent cells from the query even though static references remain in their Calc tokens. For example, Financial Model!E196 includes E85 and E86 alongside `#REF!`. The application retains those two potential edges and explicitly marks the formula partial.

No cross-sheet query disagreement was rewritten to look like success. Every cross-sheet source formula involved was also checked directly in the original worksheet XML. The token oracle agrees with all extracted edges. This is independent spreadsheet **API** precedent inspection, not a manual graphical inspection of Calc's arrow overlay or a recalculation result comparison.

The verification environment used Ubuntu LibreOffice packages extracted into a temporary prefix because system installation was unavailable. It required relocating package paths and exposing Python UNO. That environment is not a runtime dependency of Formula Map. A normal matching LibreOffice/Python-UNO installation can rerun the script as documented in README. The portable saved manifest can be replayed without LibreOffice.

## Browser workflow

`results/browser.json` records the passing real Chromium workflow in `scripts/browser_workflow.py`:

- Local file import of the valuation model and its six sheets.
- Valuation!H57 → Financial Model!D263 navigation, direct/transitive precedent tracing, and reverse dependent navigation.
- Incomplete coverage labels on the real valuation model.
- Annotation persistence across reload, rejection of Loan.xlsx as a wrong-hash reconnect, and successful reconnection of the original.
- Project JSON export/import followed by re-parsing the matching workbook.
- Offline reopening of the standalone HTML report, without script execution, including an escaped HTML-like annotation.
- All three real demo buttons and unchanged source SHA-256 values.

`results/browser.png` shows the selected source cell, annotation, coverage warning, and trace. `results/sample-report.html` is the actual browser export. The report's reached-cell list is explicitly not presented as an execution/dependency chain; the evidence table carries the real directed edges.

## Labeled controls

Eight Python tests cover quoted sheet names, absolute/mixed references, rectangular expansion, missing sheets, unsupported names/tables/external/dynamic/spill references, intersection references, shared master/follower translation, array boundaries, separate literal/cache values, archive/cell/upload limits, and XML entity rejection. Five JavaScript tests cover cycles, direct/transitive and reversed traces, traversal limits, global incompleteness, escaped report content, and report notes/anchors for blank cells. These are synthetic controls, clearly separate from the real workbooks and the independent Calc oracle.

Limits and unknown semantics are exposed rather than interpreted as a correctness guarantee. The oracle does not establish completeness for unsupported forms, formatting fidelity, macro behavior, encrypted files, financial values, or every possible legal Excel expression.
