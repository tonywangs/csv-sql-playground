# JSON Schema Review Desk

Validate local JSON, inspect offending values beside schema rules, annotate findings, and save portable reviews. Imported files are read in the browser and never uploaded or modified.

## Launch

With Node.js 20+ installed, run:

```sh
npm start
```

Open **http://127.0.0.1:8765**. The checked-in bundles need no install or network connection. If the port is busy, run `PORT=18766 npm start`. The server binds only to loopback and serves files; it has no upload endpoint. Stop with Ctrl+C.

1. Click **Load real bar-chart demo** or **Load real pie-chart demo**, then **Validate**. Both are unmodified, openly licensed Vega visualization specifications, checked against Vega's published 5.30.0 schema.
2. Click **Load labeled invalid control** and validate to inspect failures. The deliberately changed width is not a real-world defect. Select a finding to see its document pointer, schema resource/hash/pointer, value, rule, validator context, and missing-property/branch details. A missing required property points to its containing object because the missing value does not exist.
3. Filter findings and write an annotation. Export a project. Reload, then reconnect identical files (including `public/demo/CONTROL-invalid-bar.json` for the control) or load the same demo. Matching hashes recover annotations and the filter; **Validate** regenerates results. Project import follows the same procedure. Original files must be retained separately.
4. Export a JSON report and an offline HTML report. Open the HTML from disk with networking disabled. It contains inert report text, including source identities, configuration, coverage, findings, values, rules, pointers and annotations. Reports can contain sensitive input values; keep them where you keep your originals.

A [sample offline report](public/demo/sample-report.html), browser-generated report, and [actual browser screenshot](results/browser.png) are included. Successful schema validation does **not** establish factual correctness or that a visualization will render correctly.

## Exact validation behavior

- Ajv 8.17.1, JSON Schema **draft-07**. Missing `$schema` means draft-07; other dialect declarations are rejected. Core reference/applicator and draft-07 validation keywords are supported by Ajv; unknown schema keywords are rejected rather than silently ignored. There is no custom vocabulary or newer `unevaluated*`/dynamic-reference support. Schemas are meta-validated before compilation.
- `format`, content encoding/media type, and metadata are **annotations**, not assertions. An invalid-looking email can therefore pass a string/email schema. No format-assertion mode is offered. Annotation-only here means these keywords do not cause failures; the desk is not an annotation-collection engine.
- No coercion, default insertion, property removal or input writes. All failures returned by Ajv are retained (subject to execution bounds); nested combinator branches retain schema paths. Pointers refer to parsed source values, not line/column byte ranges. Schema text is never executed as application JavaScript; Ajv generates validation code internally.
- The first imported schema is the root. Reference targets must be explicitly imported with matching `$id` identifiers; local fragments and Ajv's bundled draft-07 specification resource are available. No automatic fetching, including when an input document contains `$schema` or a URL. Duplicate IDs are rejected. Finite recursive references can work; non-progressing cycles can exhaust the stack/time limit and are reported incomplete.
- UTF-8 only, no BOM; malformed encoding, malformed JSON, comments, trailing commas and duplicate object keys are rejected. Unsafe integers and non-finite numeric conversions are rejected. Other numeric values use JavaScript binary64, so decimals may be rounded and boundary/multipleOf results can differ from exact-decimal validators. This is not an arbitrary-precision validator.
- 1 MiB per file, at most 16 schema resources, parser nesting budget 80 syntax-tree levels (object property nodes count). Validation runs in a disposable worker with a 5-second wall-clock deadline, including compilation. The Interrupt button terminates it. Large/complex inputs, pathological regexes or cyclic schemas can be incomplete; incomplete never appears valid. Import parsing is synchronous but bounded. There is no operating-system memory quota.
- Recovery uses SHA-256 of original bytes, ordered schema resources and their names. No validation results are trusted from saved projects: matching sources recover annotations/settings and results are recomputed. Project files contain no originals. Browser storage may be unavailable or cleared; export a project for durable recovery. A review assumes the same pinned application/validator version.
- Statuses distinguish valid, invalid-document, invalid-schema, unresolved-reference, duplicate-resource-id, malformed-input, unsupported, resource-limit and interrupted. Reports state coverage independently. Coverage means completed validation under the stated semantics, not semantic truth or exhaustive schema annotation collection.

## Reproduce

Demo revisions, immutable source URLs/package versions, SHA-256 hashes and BSD-3-Clause license evidence are in [sources.json](public/demo/sources.json) and [LICENSE-vega](public/demo/LICENSE-vega). Acquisition verifies bytes before overwriting fixtures:

```sh
python3 scripts/acquire.py
npm ci --cache /tmp/json-npm
npm run build
npm test
node scripts/samples.mjs
python3 scripts/independent.py
npm run browser
```

The independent checker requires `jsonschema` (run tested with Python 3.12 and jsonschema 4.10.3; install with `python3 -m pip install jsonschema==4.10.3` in a virtual environment). It compares every demo/control outcome using `Draft7Validator` with formats disabled, checks source hashes and every reported pointer/value/rule, and compares atomic failure locations/keywords. Ajv emits combinator summaries alongside leaf failures; Python nests them. This presentation difference is normalized; no outcome disagreement was observed. The two engines share a specification and schema, but are separate implementations.

Browser tests require Playwright and Chromium. Install Chromium with `npx playwright install chromium`, or set `CHROMIUM_PATH` to a compatible executable. The script also recognizes the preinstalled headless Chromium in the build environment. It starts/stops a loopback server on port 18766. Tests cover both real inputs, finding inspection, annotation, reload/project recovery, changed-byte rejection, report downloads, cancellation, a deliberately pathological regex deadline, and offline HTML reopening. Actual evidence is in `results/`. Tests are Chromium/Linux only; other browsers have not been exercised.

## Design basis and existing work

This is a review workflow around established validators, not a new validation algorithm. The [draft-07 validation specification](https://json-schema.org/draft-07/draft-handrews-json-schema-validation-01) defines assertions and optional format behavior. [JSON Schema core](https://json-schema.org/draft/2020-12/json-schema-core) documents resource identities and reference concerns; this desk deliberately uses draft-07 rather than claiming newer-dialect support. [Ajv](https://ajv.js.org/json-schema.html) supplies the browser validator, while [python-jsonschema](https://python-jsonschema.readthedocs.io/en/stable/validate/) provides the independent comparison. Vega already publishes visualization schemas and examples; this desk adds local source-linked review, annotations and portable offline reports.

Additional conservative limits: asynchronous schemas and assertion siblings of `$ref` are rejected (avoiding Ajv/draft-07 sibling semantic differences). More than 5,000 findings is incomplete. False-schema failures are supported when their physical source location can be identified uniquely; an ambiguous location is reported unsupported rather than linked to a guessed rule.
