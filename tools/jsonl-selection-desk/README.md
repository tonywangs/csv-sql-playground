# JSONL Selection Desk

A local browser workbench for inspecting nested JSONL records, making explicit typed selections, and exporting original record bytes with a verifiable manifest.

## Launch

Requires Python 3.10+; no application dependencies or accounts.

```sh
python3 desk.py
```

Open **http://127.0.0.1:8765**. The server binds only to loopback. Use `--port 8766` if needed. Stop with Ctrl+C. The application does not send data to external services or write uploaded files to disk.

1. Click **Load real earthquake demo**, or open your JSONL file.
2. Click any source line to inspect nested objects and arrays. Original numeric spelling is retained in the inspector.
3. Add `/properties/mag`, **number ≥**, `5`. The pinned real dataset has **13 included, 98 excluded, 0 errors**. Filters combine with AND. Uncheck a record to exclude it even if it matches.
4. **Save project** downloads filters, exclusions and the source hash. Reloading finds the last project in browser local storage; reattach the same file to recover it. **Restore project** also works in a fresh browser. Restoring against an attached different source is rejected. Attaching a different file starts a new selection; save the old project first if you want to retain it.
5. **Export subset + manifest** downloads a ZIP containing `subset.jsonl` and `manifest.json`. Extract it, independently verify it, then open `subset.jsonl` in the app to inspect the result.

![Real USGS data in the browser, filtered to magnitude 5 and greater](docs/demo.png)

## Paths and types

Paths use [JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901): `/properties/mag`, `/geometry/coordinates/2`; an empty path means the whole record. Escape `/` in a key as `~1` and `~` as `~0`. Array indexes are nonnegative decimal integers without leading zeros; wildcards are not supported. A path that cannot be resolved is **missing**, distinct from an explicit `null`.

- **equals** accepts a JSON scalar: `"5"` (string), `5` (number), `true`, `false`, or `null`. There is no coercion. Objects and arrays can be selected by type, but not by structural equality.
- **number >, ≥, <, ≤** compare exact decimal values. Boolean `true` never equals numeric `1`. Numbers with different spellings but equal mathematical values, such as `1` and `1e0`, compare equal.
- **has type** takes one unquoted type name: `missing`, `null`, `string`, `number`, `boolean`, `array`, `object`.
- A checkbox means “allow this line if all filters match.” It cannot override a failed filter. Every imported line is shown as included, excluded or error. Choose **Errors** to inspect error messages and line numbers.

## Byte preservation and accounting

The parser splits on LF only. Each original line retains LF, CRLF, or its absent final terminator. Export concatenates selected original line byte slices in source order, never reserializes records, and never adds a final newline. An unterminated source line can only be the final exported line. The source is never modified. Empty files have zero lines; a trailing LF does not create a phantom line.

The manifest records SHA-256 of the complete source and output, byte counts, one-based source line numbers, filter settings, manual exclusions, all error line numbers/messages, and counts satisfying **total = included + excluded + errors**. “Complete” means every line was classified, not that every line was valid. Error lines cannot be exported. Exported subsets may be empty.

```sh
python3 tools/verify_export.py data/earthquakes.jsonl examples/magnitude-5.jsonl examples/magnitude-5.manifest.json
```

The standalone verifier independently parses the source, evaluates filters, reconstructs expected bytes, checks ordering, hashes and accounting. It imports no application code. Browser tests additionally compute the real-data selection and bytes using JavaScript. Synthetic adversarial controls have explicit expected line numbers and are labeled in the tests.

## Real data and existing work

The demo is a **111-event USGS catalog sample for January 1, 2024**, magnitude ≥2.5, ordered by time. Nested properties and geometry arrays are real catalog data. Credit: U.S. Geological Survey / Department of the Interior. USGS-produced data is U.S. Public Domain; this fixture contains event data, not third-party imagery. See [provenance, rights evidence, URLs and hashes](data/PROVENANCE.json) and the retained [original GeoJSON response](data/usgs-source.geojson).

**Source-format conversion is explicit:** `tools/acquire.py` serializes each GeoJSON feature as one compact UTF-8 JSONL record. Byte-preservation claims begin at that resulting JSONL file, not at the HTTP response. The source revision is pinned by the retained response hash and catalog metadata; upstream catalog records can change.

```sh
python3 tools/acquire.py --check  # offline: verify the exact pinned conversion
python3 tools/acquire.py --fetch  # optional network: replace snapshot with current catalog revision
```

Design references: [JSON Lines](https://jsonlines.org/) for UTF-8 and LF records; [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) for JSON values and interoperability constraints; [USGS GeoJSON format](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php). Existing [jq](https://jqlang.org/manual/) supplies expressive command-line JSON filtering, while [Datasette](https://datasette.io/) offers browser-based structured-data exploration. This project combines a small typed filter UI with original-line-byte export and provenance; it makes no novelty claim.

## Limits

- At most **8 MiB per file**, **20,000 physical lines**, **256 KiB per line**, **64 nesting levels**, **30 filters**. Numbers permit up to 1,000 token characters and absolute adjusted decimal exponent ≤10,000. File/line-count failures reject the import as incomplete and disable export. Per-line failures are explicit errors; remaining lines still get classified.
- UTF-8 decoding is strict. Blank lines, malformed JSON/UTF-8, BOM-prefixed values, duplicate object keys, unpaired escaped surrogates, NaN/Infinity and over-limit records are errors. The error inspector replaces undecodable bytes for display only. Original bytes stay unchanged. Lone CR is JSON whitespace, not a record separator. Scalar and array roots are valid records.
- Entire source bytes and parsed records live in server memory. This is a bounded desktop tool, not a streaming large-data processor. Memory depends on shape and Python object overhead; no fixed RSS ceiling is promised. Parsing runs synchronously, so an import may briefly pause the UI.
- One active source per server process. Other tabs can replace it; hash checks reject stale queries/exports. Run separate ports for separate workspaces. Not intended as a multi-user or remotely hosted service.
- Browser local storage saves only the latest project, not source bytes. Clearing browser storage loses that recovery copy. Download projects for durable storage. Project files disclose filters, source name/hash and excluded line numbers; keep them appropriately private.
- No authentication beyond local origin/session protections, no compression imports, regex, OR groups, wildcard arrays or schema inference. No telemetry, external scripts or automatic network acquisition.

## Verification

Core checks are offline and need only Python:

```sh
python3 -m unittest discover -s tests -v
python3 tools/acquire.py --check
python3 tools/verify_export.py data/earthquakes.jsonl examples/magnitude-5.jsonl examples/magnitude-5.manifest.json
```

Full browser acceptance test (Node 20+, Playwright/Chromium required for testing only):

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

For restricted environments, set `npm_config_cache=/tmp/jsonl-npm-cache` and `PLAYWRIGHT_BROWSERS_PATH=/tmp/jsonl-browsers` for installation and the browser test. The browser test starts its own ephemeral local server, exercises the full workflow on the pinned data, audits the downloaded export, covers error/precision controls, and updates `docs/demo.png`. It does not require a running app or network once Chromium is installed.
