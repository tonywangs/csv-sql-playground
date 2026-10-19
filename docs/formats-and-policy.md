# Policy and interchange formats

## Read-only and resource boundaries

Each query uses a new subprocess and a private, server-owned snapshot opened with `mode=ro&immutable=1`. SQLite `query_only=ON`, disabled extension loading, `trusted_schema=OFF`, and an authorizer allowlist are applied before preparing user SQL. The authorizer allows SELECT, READ, recursive CTE operations, and the explicitly listed built-in functions in `desk/core.py`; all other actions are denied. This rejects DDL/DML, transactions, PRAGMA, ATTACH/DETACH and extension loading without relying on SQL keyword matching. SQL must be one statement. Functions outside the allowlist are unsupported even if normally read-only. A connection is not reused between queries.

Limits:

| Resource | Default | Maximum |
|---|---:|---:|
| Imported database | — | 8 MiB |
| Tables | — | 100 |
| SQL text | — | 64 KiB |
| Result rows | 1,000 | 10,000 |
| Typed row/column JSON payload | 1 MiB | 4 MiB |
| Execution duration | 3 seconds | 10 seconds |
| Columns | — | 256 |
| Named parameters | — | 100 |
| SQLite value length | — | 4 MiB |
| Saved queries | — | 100 |
| Imported project JSON | — | 1 MiB |

The byte limit counts UTF-8 compact JSON for the column array and row array, including array delimiters and row separators, but excludes execution metadata and the ZIP/CSV encodings. A single oversized column list can exceed the chosen byte cap; no rows are then returned, and the status is truncated. A SQL value exceeding SQLite's own 4 MiB cap fails with an error rather than truncation. All rows are materialized within the bounded worker. Linux workers additionally have a 384 MiB address-space ceiling and 15-second CPU ceiling. Availability of OS resource limits varies; wall-time termination remains enforced by the parent on all supported Python platforms. This is not a whole-server or whole-browser memory quota.

SQLite's progress callback interrupts long execution. The parent kills a worker after the configured duration plus 250 ms of process-start/IPC grace. User cancellation also kills the worker; process termination is checked every 50 ms. A parent-killed worker returns no rows, because uncommitted worker output is discarded. A SQLite-interrupted query may retain a prefix of fetched rows. Both are explicitly `interrupted`, never `complete`. Schema inspection uses its own three-second worker timeout.

## Completion states

- `complete`: cursor exhausted, including a successful empty result. Exactly reaching the row cap is complete only if the next fetch confirms exhaustion.
- `truncated`: another row would exceed the row or byte cap (or column metadata exceeds the byte cap). A prefix is not the full answer, and aggregates can still be partial when a query returns multiple groups.
- `interrupted`: cancellation or time limit. Results may be empty or a prefix. Acknowledgment is required even for an empty interrupted export.
- `error`: malformed SQL, denied operation, decoding, resource, or execution failure. Rows are discarded; export is refused.

All exports bind to the executed SQL and parameters, not subsequent editor changes. The browser labels a result stale when the editor changes; rerun to export the edited analysis. An export records result count, not the unknown total number of rows for incomplete output. `source_unchanged` compares snapshot SHA-256 before and after execution to the imported identity. No query or export silently reconnects a changed source.

## Types and formats

`sqlite-query-desk.result.v1` is a JSON object containing `source` (name, byte count, SHA-256), exact SQL, parameter specifications, settings, SQLite version, ordered `columns`, ordered `rows`, status, reason, row count and hash-check result. Rows are arrays rather than objects so duplicate column names and their original positions survive.

Each cell is `{ "type": ..., "value": ... }`:

| Type | JSON value |
|---|---|
| null | `null` |
| integer | Decimal string, preserving signed 64-bit precision |
| real | Python round-trippable float string, including `inf`/`-inf` if SQLite returns them |
| text | Unicode string |
| blob | Standard base64 string |

SQLite's dynamic cell type is preserved, not inferred from declared column types. SQLite may convert numeric expressions and normalize NaN to NULL. Input real parameters must be finite; integer parameters must be signed 64-bit decimal strings. Named parameters use `:name`, `$name` or `@name`; positional `?` binding is unsupported. Extra named bindings follow Python SQLite behavior and may be unused.

Text must decode as UTF-8 through Python SQLite; invalid text fails visibly. NULL differs from empty text and empty BLOB in typed JSON. Without `ORDER BY`, row order is unspecified. Even `ORDER BY` requires enough tie-breakers for repeatable ordering.

`results.csv` is UTF-8, with a header, comma separators, CSV quoting, and CRLF rows. NULL and empty text both become empty fields, integers/reals become their string values, and BLOBs become base64. CSV does not preserve types. Formula-like strings are kept byte-faithful rather than prefixed: import CSV columns as text, or use typed JSON, when opening in a spreadsheet.

`sqlite-query-desk.manifest.v1` separately records all execution metadata and SHA-256 of the exact CSV and typed JSON bytes. Its `partial_acknowledged` flag records the exporter's explicit choice. Hashes provide integrity checks, not signatures or proof of trustworthy input. Export archives contain only three fixed filenames. Source SQL/parameter metadata may include sensitive information.

`sqlite-query-desk.project.v1` records named editor states, parameter JSON text, execution limits, selected index and last source identity. Invalid in-progress parameter text can be preserved for editing. Invalid limit settings or a serialized backup exceeding the 1 MiB import limit prevent project export. The editor is locked while a query runs to keep completion attached to the visible statement. Query results and source bytes are deliberately absent; a portable result ZIP is their separate historical record.

## Unsupported inputs and platform limits

Encrypted/SQLCipher databases, live databases, WAL-mode headers/companions, external attachments, virtual tables/extensions, user-defined functions/collations, and non-UTF-8 text values are unsupported. Ordinary views may work with allowed built-ins; trusted-schema restrictions may reject a view. Only ordinary table columns are listed in the schema panel (generated/hidden columns are not enumerated by `table_info`). The app is not a SQL dialect converter.

The browser cannot detect unselected companion files, concurrent source writes, or an incorrectly made snapshot. The user must supply a stable export. Header checks do not establish that an arbitrary file is a consistent backup. SQLite validates pages it reads, not an exhaustive integrity check of all pages. The imported snapshot is never modified by SQLite. No telemetry, third-party scripts, external styles or network dataset fetches occur during launch/use.

The HTTP service binds only to 127.0.0.1, validates Host, rejects cross-origin mutations, requires a per-process token, and uses a restrictive content security policy. It has no remote access or multi-user authentication. Run one tab at a time. A same-user local process can access the service; this is not an authorization barrier against another process on your machine.
