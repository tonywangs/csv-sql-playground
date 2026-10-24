# Pinned real-data comparison

The demo compares complete March and October 2026 repository snapshots of the
World Bank population CSV using `Country Code` + `Year`. These are actual dataset
revisions, not synthetic changes. [Provenance, licenses and acquisition](../data/population/README.md)
identify the exact bytes and attribution.

```sh
python3 scripts/demo.py
```

| Classification | Groups | Before records | After records |
| --- | ---: | ---: | ---: |
| Unchanged | 15,723 | 15,723 | 15,723 |
| Changed | 1,407 | 1,407 | 1,407 |
| Added | 264 | 0 | 264 |
| Removed | 65 | 65 | 0 |
| Unresolved | 0 | 0 | 0 |
| **All accounted** | **17,459** | **17,195** | **17,394** |

There are no duplicate keys, missing keys or schema differences in these two
inputs. Thus this real-data run validates definite additions/removals/changes;
it does **not** provide real-world evidence about duplicate-key ambiguity.
Controlled tests cover that behavior separately.

Examples checked against the original source records:

- Added `ABW / 2025`: Aruba, population `108785`, after row 66 / physical line 67.
- Removed `FCS / 1960`: Fragile and conflict affected situations, `244461631`,
  before row 4811 / physical line 4812.
- Changed `AFW / 1964`: Africa Western and Central, value `106388440` → `106384410`,
  before row 200 / line 201 and after row 203 / line 204.

These are differences between CSV snapshots, not judgments about the correctness
of population estimates. Removed aggregate data can reflect upstream packaging
or scope changes; the comparison does not infer their cause.

## Independent verification

`scripts/verify_population.py` does not import the reconciliation implementation.
It loads original inputs into SQLite tables with primary-key constraints and uses
joins/anti-joins to independently derive classifications. It then checks every
report event, source cell, row/line reference, changed field and aggregate count.
The independent result agrees with the table above for all 17,459 groups and all
34,589 input records. It also checks input hashes against the provenance manifest.
The verifier deliberately supports this unique-key dataset; the application's
broader duplicate and missing-key behavior is checked by the controlled suite.

Run it on a separately generated or installed-CLI result:

```sh
python3 scripts/verify_population.py demo-output/comparison.json
```

## Reproduction and limitations

The 20 controlled tests include 100 randomized cases with seed `20261019` that
check complete source-record conservation and exact multiset cancellation.
The actual Python 3.12.3 run passed. A wheel installation into an isolated
environment and the installed `csv-reconcile` entry point were exercised outside
the source checkout on the complete real inputs; the resulting JSON passed the
same independent verifier. No performance benchmark or large-file scalability
claim is made. See [testing instructions](testing.md) for repeatable checks.

Offline Chromium browser checks passed on the real report and a controlled
ambiguity/multiline/injection fixture. They exercised all status filters, search,
pagination, expanded source references and mobile width without external requests
or JavaScript errors. The [screenshot](demo.png) shows the actual generated report.
