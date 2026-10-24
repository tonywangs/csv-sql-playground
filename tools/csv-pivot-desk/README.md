# CSV Pivot Desk

A local browser workbench for summarizing a CSV and inspecting every contributing record. Nothing is uploaded to a service. Requires Python 3.10+; no runtime dependencies.

```sh
python3 server.py
```

Open **http://127.0.0.1:8765** and choose **Try the penguins demo**. Or open a local CSV, declare the value column as Number, choose row and optional column groups, and apply Count, Sum, or Mean. Use the raw-text filter to narrow the result. Every result and grand total has an **Inspect** button; missing and invalid numeric values are separately labeled. Inspect filtered and structurally rejected records from their own buttons.

The real demo shows body mass by species and island for 344 Palmer penguins. It has 342 valid body-mass observations and two missing values. The overall mean is 4201.754385964912 g, calculated from the 342 records, not from displayed group means. This is an exploration example, not a biological inference.

## Save, recover, and share

- Applied configuration is saved in browser local storage; the CSV bytes are not persisted there. After a reload, reconnect the original CSV. SHA-256 must match, even if the filename changed. Clear workspace starts a different source.
- **Save project configuration** produces a small JSON file. **Restore project** loads it and asks for the matching source. Project files contain configuration and source identity, not the CSV.
- **Export report bundle** downloads a ZIP with `summary.csv`, `report.html`, `audit.json`, `project.json`, and `manifest.json`. Unzip and open `report.html` in a browser: every group has native expandable source-record tables. No server, JavaScript, or internet is required for the report. Original source values are included in the report and audit; treat exports with the same privacy as the source.
- The manifest records the source hash and size, applied configuration, typing and precision rules, aggregate definition, accounting, and SHA-256 hashes for all four other output files. It does not hash itself or the ZIP. Hashes detect changes; they are not signatures or proof of authorship. Verify against your original CSV with the separate implementation below.
- Categories in the summary CSV are JSON-encoded strings: `"001"` remains an identifier; JSON `null` represents no column grouping or the grand total. This also avoids formula-leading category cells. `scope` distinguishes totals. Undefined numeric results are empty CSV cells and `null` in JSON; actual zero is `0`.

Checked-in [sample report](examples/report.html), [summary CSV](examples/summary.csv), and [manifest](examples/manifest.json) provide a visible real-data example. Open the HTML locally, or use the demo button in the running app. Dataset provenance, pinned revision, hashes, license, and reacquisition command are in [data/source.json](data/source.json); the upstream [CC0 license](data/LICENSE.md) is included. Data: Kristen Gorman and Palmer Station LTER; package: Horst, Hill, and Gorman (2020), [doi:10.5281/zenodo.3960218](https://doi.org/10.5281/zenodo.3960218).

## Input and calculation contract

- UTF-8 only, with optional BOM. Comma-separated, double-quoted fields with doubled quote escaping; LF or CRLF record endings. Quoted commas and newlines are preserved. No automatic delimiter or encoding guessing. The Python CSV strict parser defines accepted quoting; this is not a full RFC lint tool.
- Nonempty unique headers are required. Duplicate headers reject the whole file; they are never silently renamed. Every parsed data record gets a stable 1-based ordinal after the header. A quoted multiline record has one ordinal. Blank records and wrong-width records are explicitly rejected and retained with raw field arrays. Their ordinals are never reused.
- Categories, including empty strings, whitespace, Unicode, leading zeros, and `NA`, are preserved exactly. Numeric missing tokens do not collapse category labels. All columns start as Text. The built-in demo explicitly selects Number for body mass and uses `["", "NA"]` for missing values.
- Numbers accept an optional sign, up to 18 integer digits and 12 fractional digits, and a decimal point with digits after it. `.5` and `+2` work. Whitespace, thousands separators, exponents, `NaN`, infinities, and excess precision are invalid, not coerced. Missing tokens match exact raw strings before numeric parsing. Source strings are never rewritten.
- Count counts all included records. Sum and Mean require an explicitly numeric value column and exclude missing/invalid values. Valid, missing, and invalid counts and record sets are visible alongside numeric results. Typing a non-value column as Number does not discard rows; types control whether a selected value column may be numerically aggregated. Filters compare raw text regardless of declared type.
- Sums use exact decimal arithmetic within the supported digit and record limits. Means round once to 12 decimal places using ties-to-even. Totals use all contributing records directly. Empty/no-valid numeric sets are undefined, including sums. A zero count is zero. Unobserved row/column combinations are absent; observed groups with no valid values remain visible as undefined. The display is a sparse grouped table, not a dense cross-tab grid.
- Filters: one browser-editable Equals, Not equal, or Contains condition, case-sensitive and untrimmed. The engine supports up to 10 ANDed filters; the browser explicitly rejects multi-filter projects rather than dropping filters. No numeric comparisons or computed expressions.
- Limits: 2 MiB source, 10,000 parsed records, 40 columns, 10,000 characters per data field, 500 observed groups, 20 missing tokens (100 characters each). Invalid syntax, unsupported configuration, or exceeded limits fail the whole operation. Export is also rejected if an individual output exceeds 10 MiB or combined outputs exceed 24 MiB. Filtering can reduce report size. The browser does not paginate source inspection, so large tables may be slow.
- The server binds only to `127.0.0.1`, checks Host/Origin, and exposes only fixed assets and stateless analysis routes. Do not expose it through a public proxy. The original file is read into memory and never modified. Browser storage availability and browser downloads depend on browser settings. No collaboration, automatic file watching, XLSX, authentication, or hosted deployment.

## Reproduce and verify

```sh
python3 scripts/acquire_demo.py                 # optional network reacquisition; asserts pinned hashes
python3 -m unittest discover -s tests -v
python3 scripts/make_demo.py
python3 scripts/verify_report.py data/penguins.csv examples
npm ci --cache /tmp/csv-pivot-npm-cache          # browser tests only
npx playwright install chromium                # once, if Chromium is not installed
npm run test:browser
```

`tests/browser.cjs` starts its own local server and uses a fresh browser profile. It tests the demo, local import, typing, grouping, filters, source inspection, failed configuration, source mismatch, reload recovery, project transfer, ZIP export, and standalone report reopening. It independently verifies the downloaded bundle against the original CSV. Optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` selects an installed Chromium. Optional `CSV_PIVOT_ARTIFACT_DIR` preserves screenshots and exported artifacts outside the repository.

The independent verifier imports no application code: it reparses source CSV, derives groups and filters separately, uses exact rational arithmetic, checks every aggregate and contributing-record set, validates record accounting and all output hashes, and compares summary CSV cells and HTML drill-down rows with original records. Unit controls cover missing and invalid numbers, negatives, decimals, duplicate records, leading-zero identifiers, Unicode, quoted newlines, empty categories, empty results, unequal group sizes, precision and limits. These labeled controls complement the real demo; they do not substitute for it.

## Existing work and design references

This is not a novel aggregation method. [Python CSV documentation](https://docs.python.org/3/library/csv.html) motivates preserving strings and explicit dialects; [Decimal documentation](https://docs.python.org/3/library/decimal.html) supports explicit decimal rounding. [pandas pivot_table](https://pandas.pydata.org/docs/reference/api/pandas.pivot_table.html) provides grouping, aggregation, margins, and missing-value options; [PivotTable.js](https://github.com/nicolaskruchten/pivottable) provides a mature interactive pivot UI. This smaller dependency-free implementation emphasizes stable record ordinals, explicit exclusions, hash-bound recovery, and independently checkable portable outputs. The [primary dataset documentation](https://allisonhorst.github.io/palmerpenguins/) describes source collection and CC0 availability.
