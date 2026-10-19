# JSON format, version 1

The CLI emits a UTF-8 JSON document with a trailing newline. Object keys are
sorted; keys are grouped in lexicographic string order. The document has no time
or absolute-path fields. It can be pretty-printed with `python3 -m json.tool`.

| Field | Meaning |
| --- | --- |
| `format_version` | Currently `1` |
| `keys` | Selected column names, in CLI order |
| `delimiter` | Explicit input separator |
| `sources.before`, `sources.after` | Basename, original byte SHA-256, byte count, ordered columns, record count |
| `schema` | Added/removed columns and whether the same columns were reordered |
| `summary.<status>` | Event-group count and before/after record counts |
| `duplicate_keys` | Every nonempty key repeated on either side and its original multiplicities |
| `accounting.<side>` | Input count and accounted record count |
| `events` | Complete record partition, including unchanged and unresolved records |

Every event has a sequential `id`, `status`, `key` (a string array, or `null` for
missing keys), `before` and `after` record arrays. Each record has `row`,
`line_start`, `line_end` and `values`. `values` maps original column names to
strings; it never loses a cell or collapses duplicate source records. `row` is a
1-based data-record index excluding the header. Physical line numbers include the
header. A multiline record has one row number and a multi-line inclusive range.
Source identity is the enclosing `before`/`after` side and its source hash.

An `unchanged` event has one record on each side. `added` has one after record and
no before record; `removed` is the reverse. A `changed` event has one record per
side and a `changes` array of `{column, before, after}`. JSON `null` in a change
means that column did not exist, while `""` means an existing empty cell.

An `unresolved` event has `reason` equal to `duplicate_key` or `missing_key`.
Duplicate ambiguity retains all residual records in arrays and implies **no
positional pairing**. A missing-key event contains one source record on one side;
it implies neither an addition/removal nor a match. There is no `changes` array
for unresolved events.

Exact duplicate matches are deterministic multiset cancellations in source order.
Do not interpret their selected row references as proof that those individual
identical records have the same real-world identity. Input order changes source
row references and can therefore change JSON bytes even if multiset totals agree.
