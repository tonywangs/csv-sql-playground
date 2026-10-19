# CSV Join Desk

Combine two local CSV tables with explicit keys, inspect unmatched records and duplicate-driven row multiplication, and export a table with a verifiable source trail.

## Launch

Requires Python 3.10+; the application has no third-party runtime dependencies.

```sh
python3 app.py
```

Open **http://127.0.0.1:8765**. Click **Load real airport demo**, then **Inspect keys & estimate output**, then **Build preview & export**. Download both the CSV and manifest. To use your own data, select two UTF-8 CSV files and choose their corresponding key columns. Use **Add key component** for a composite key; component order matters.

The bundled real demo joins 300 OurAirports large-airport records to 249 country records. Its full outer join produces **471 rows**: 300 matches and 171 unmatched country records. The airport subset has 51 duplicated country keys, the country table has none. These are subset coverage gaps, not evidence of defective source data. [Sample CSV](examples/joined.csv) and [manifest](examples/joined.manifest.json) are ready to inspect. [Demo screenshot](docs/demo.png) shows the local workflow.

Choose inner, left, or full outer join; declare one-to-one, many-to-one (unique right keys), or unrestricted. Inspection shows each key's source record ordinals and multiplicities, all unmatched records with values, missing-key records, and expected output rows. Many-to-many matches require acknowledgment. Change the configuration to resolve a blocked join, then inspect again. The result preview shows the first 100 rows; the export includes all rows.

## Recovery and verification

Settings are saved in browser local storage, without source contents. After reloading, select both original files and click **Restore matching project**. Both file hashes must match. Export/import project settings to move the configuration to another browser; transfer the originals separately. Files are not modified or saved by the server. **Forget saved project** deletes local settings.

Every export includes `_left_record` and `_right_record`, even if all data columns are deselected. Ordinals are 1-based **data records**, excluding headers; embedded newlines do not increment the ordinal. Blank provenance means an absent source record; an empty value with a present ordinal is a real empty field. The separate manifest records source SHA-256 hashes, configuration, counts, all emitted pairs, missing/unmatched ordinals and output hash.

Verify downloaded files independently (substitute their paths):

```sh
python3 scripts/verify_export.py data/airports.csv data/countries.csv examples/joined.csv examples/joined.manifest.json
```

The verifier does not import application code. It uses a nested-loop join rather than the application's indexed join, compares every cell and pair, checks order, counts, and hashes, and rejects tampering. It is intended for bounded exports, not large production tables. Browser tests additionally reopen exports using the independent JavaScript `csv-parse` parser.

## Semantics and limits

- All values are strings. No type inference, trimming, case folding, locale collation or Unicode normalization. `01` differs from `1`; composed and decomposed accents differ; `NA` is a literal value. If **any** key component is empty, the record never matches another record, including another missing key.
- Duplicate multiplicities are preserved: a key with m left records and n right records emits m × n matched pairs. Relationship validation considers every nonmissing key, including unmatched keys; missing keys are separately reported and excluded from uniqueness assertions.
- Output is deterministic: left records in input order, each matching right record in input order, then (full outer only) unmatched right records in input order. Inner joins omit unmatched records from output but retain their accounting in the manifest.
- Input: comma delimiter, required unique nonempty headers, double-quote escaping, quoted newlines, UTF-8 with optional BOM, LF/CRLF/CR line endings, Python `csv.reader(strict=True)` dialect. Spaces are data. No delimiter guessing. Blank lines, ragged records, invalid UTF-8, NUL, duplicate headers, and unterminated quoted fields reject the **whole file**. No partial result is offered. The parser's dialect is not a complete RFC grammar validator (it accepts literal quotes inside unquoted fields). See [design references](docs/design.md).
- Each input is limited to 2 MiB, 10,000 records, 100 columns, and 131,072 characters per field. Output is limited to 20,000 rows and a conservative 8 MiB CSV byte bound; the user may lower the row limit. Both limits are checked by multiplicity **before** row-pair materialization. The conservative byte check may reject an output smaller than 8 MiB. JSON requests are limited to 6 MiB. Output manifests may be larger than CSVs because they include pair arrays.
- A source error leaves the configuration/results unavailable until both valid sources are imported. All accepted input records appear in a matched-key group, an unmatched-key group, or the separate missing-key list. There is no silent record filtering.
- Local browser and loopback server only. The server accepts the printed `127.0.0.1` origin, keeps no database, and serves only application/demo assets. Do not expose it through a public proxy. No network is needed during normal use. Settings persist only if browser storage is available; export settings otherwise. Sources must be reselected after closing/reloading.
- CSV formula strings are preserved for fidelity. When opening untrusted CSVs in spreadsheet software, import columns as text. This tool does not sanitize formulas or provide spreadsheet execution protection.
- Bounded in-memory workbench; no streaming joins, fuzzy matching, filtering, transformations or asynchronous job queue. It is not an aviation navigation data product; upstream data has no fitness guarantee.

## Reproduce the data and tests

The pinned source revision, license evidence, input hashes and upstream-to-subset record maps are in [data/provenance.json](data/provenance.json) and [data/LICENSE](data/LICENSE). Acquisition keeps every column and original field value, selects the first 300 `large_airport` rows in source order, retains all countries, and reserializes CSV using CRLF. No synthetic records are mixed into the demo. Full upstream downloads are temporary memory inputs; only the bounded subsets are stored.

```sh
python3 scripts/acquire_demo.py
python3 scripts/make_example.py
python3 -m unittest discover -s tests -v
python3 scripts/verify_export.py data/airports.csv data/countries.csv examples/joined.csv examples/joined.manifest.json
```

Acquisition requires public network access. The other Python commands run offline. Reacquisition should produce unchanged tracked data and examples.

For the browser checks (Node 20+):

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

`CHROMIUM_PATH=/path/to/chrome npm run test:browser` uses an existing browser. Browser checks start/stop their own loopback server, use a temporary directory for downloads, verify the real export with a second CSV parser and the Python oracle, and exercise recovery, hash mismatch, invalid input, relationship rejection, composite/missing/multiline/Unicode controls and expansion limits. `JOIN_SCREENSHOT=/absolute/path.png` saves an optional screenshot. Tests use labeled synthetic controls only to cover edge cases absent from the real demo. Unit tests include 36 seeded oracle comparisons across inner, left and full outer joins (seed 7239).
