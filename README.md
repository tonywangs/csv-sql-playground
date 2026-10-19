# Formula Map

A local browser explorer for XLSX formula dependencies. Follow inputs and dependents across sheets, annotate source cells, recover a review, and save a standalone report. It never recalculates or modifies a workbook.

## Run

Requires Python 3.10+ with `venv`/pip (on Debian/Ubuntu, the `python3-venv` package) and a modern browser. First launch installs the pinned Python dependencies; subsequent launches work offline.

```sh
./launch.sh
```

Open **http://127.0.0.1:8765**. If that port is occupied, use `./launch.sh --port 8876` and open port 8876. The server binds only to loopback and checks Host/Origin headers. Do not expose it through a public proxy.

1. Choose **Six-sheet valuation model**, or import a local `.xlsx`.
2. Select sheet **Valuation**, enter **H57**, and follow its reference to **'Financial Model'!D263**. Switch between precedents/dependents and direct/transitive traces.
3. Write a source-linked review note. Reload, reconnect the same workbook, and verify your selection and note return. A different workbook hash is rejected.
4. Export **project JSON** to back up source identity, evidence and notes. Import it and reconnect the original XLSX to resume. Use **Start new review** before switching workbooks; export first if you need to preserve the old review.
5. Export **offline HTML** and open it without the server. Its cell links, evidence tables, annotations and full JSON remain available offline.

See [sample standalone report](results/sample-report.html) and [browser screenshot](results/browser.png). Download the HTML to open locally; GitHub's file view is not the rendered report. The included sample has a labeled review note containing literal HTML-like text to demonstrate safe escaping.

## Real demos and provenance

Three MIT-licensed workbooks from Packt's *Hands-On Financial Modeling with Microsoft Excel 2019* examples are retained, with exact upstream revision, immutable URLs, byte counts, SHA-256 hashes, and license evidence in [fixtures/sources.json](fixtures/sources.json) and [fixtures/LICENSE](fixtures/LICENSE). They were authored for practical loan, cash-flow, and valuation modeling instruction, rather than parser testing. The financial data are illustrative, not verified real-company valuations. `Valuation.xlsx` retains the original bytes of the longer upstream filename.

```sh
python3 scripts/acquire.py             # verify retained bytes
python3 scripts/acquire.py --download  # reacquire pinned public bytes and verify before saving
```

The valuation model deliberately exposes limitations found in a real source workbook: broken references and unresolved forms remain visible. It is not silently repaired. Dependency support is not a guarantee of financial or calculation correctness.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/graph.test.js
.venv/bin/python scripts/verify_manifest.py
python3 scripts/check_tree.py
```

The recorded manifest is generated independently from LibreOffice Calc's formula-token reference structures, for **every supported and partial formula** in all three demos. Calc's precedent-query API is also compared; its ten cross-sheet query mismatches are retained and documented. Replay verifies that current edges still match the saved oracle. To regenerate the oracle, install LibreOffice Calc and Python UNO for the same Python version, then run `.venv/bin/python scripts/verify_libreoffice.py`. `SOFFICE` can select an executable; nonstandard UNO installations also need `PYTHONPATH` and library paths. See [verification notes](docs/verification.md) for the actual results and method limits.

For a fresh browser acceptance run:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser_workflow.py
```

The browser test starts an isolated loopback server and checks real import, cross-sheet navigation, both trace directions, notes, reload, wrong-hash rejection, JSON recovery and offline report reopening. It does not require an existing server.

## Limits

- Input: unencrypted transitional OOXML `.xlsx`; no `.xls`, encrypted Office container, strict OOXML or non-worksheet sheets. Macros are not executed. Charts, styles, drawings, comments and formatting are not rendered. Numeric/date literals are raw stored values, not formatted display values.
- Up to **10 MiB** input, **32 MiB** total uncompressed archive data, **1,000** archive members, **50,000** stored cells, **8,192** characters per formula, **10,000** expanded cells per reference range, **200,000** extracted evidence edges. Oversized files/archives/cell counts are rejected; oversized formulas/ranges/edge sets are explicitly unresolved.
- Trace: **10,000** visited nodes; results report traversal truncation. UI shows at most **500** filtered cells and **1,000** trace edges; address navigation and full exports remain available. Notes: **10,000** characters per cell. Browser storage quota failures prompt export. Imported project JSON: **32 MiB** maximum.
- Named/structured/external/3D/whole-row/whole-column references, dynamic references, array/data-table and spill semantics remain unresolved. Shared A1 formulas are translated from their masters. See [design and source research](docs/design.md) for the exact policy.
- Any unresolved formula makes transitive results conservatively incomplete, even if it appears unrelated. Cached results have **unknown freshness**. Static edges are potential dependencies and not proof of branch execution, correctness, or successful recalculation.
- Workbook bytes are never saved by the server or embedded in reports. Keep original workbooks with exported JSON. Notes are browser-local and contain no authentication or collaboration features. Reports include source cell contents; share them only when appropriate for the workbook.

No hosted service or publication is required.
