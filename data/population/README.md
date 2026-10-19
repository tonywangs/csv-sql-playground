# Public population revisions

These are **complete, unmodified CSV files**, not generated or sampled data.
They were acquired on 2026-10-19 from the public
[datasets/population](https://github.com/datasets/population) repository.
The repository converts [World Bank population, total (SP.POP.TOTL)](https://data.worldbank.org/indicator/SP.POP.TOTL)
to CSV, including countries and aggregate regions. Commit dates identify these
repository snapshots; they are not claims about the underlying observations'
publication dates. The package metadata has a stale `last_updated` value, so this
project uses immutable commit identifiers and content hashes instead.

| Local file | Upstream commit | Commit UTC | Records | Bytes |
| --- | --- | --- | ---: | ---: |
| before.csv | 425fc447a53a26c767a15a7de60c4cc2478a0595 | 2026-03-06 11:27:07 | 17,195 | 552,112 |
| after.csv | d4b1a4a9a17e2123baf0ef119de05bceced1ab1b | 2026-10-01 02:32:39 | 17,394 | 556,718 |

The explicit comparison key is `Country Code` + `Year`. Country name and value
are compared as strings. Both revisions independently satisfy key uniqueness.
SHA-256 hashes and exact download URLs are recorded in [provenance.json](provenance.json).

## Acquisition

From the project root, reacquire the exact bytes, verify their hashes, generate the
report and verify it independently:

```sh
python3 scripts/demo.py --fetch
```

Equivalent download commands (the demo still checks the hashes afterward):

```sh
curl -fL https://raw.githubusercontent.com/datasets/population/425fc447a53a26c767a15a7de60c4cc2478a0595/data/population.csv -o data/population/before.csv
curl -fL https://raw.githubusercontent.com/datasets/population/d4b1a4a9a17e2123baf0ef119de05bceced1ab1b/data/population.csv -o data/population/after.csv
python3 scripts/demo.py
```

Normal demonstration and validation are offline using the bundled bytes. Only
`--fetch` requires network access. This project makes no claim to ship the latest
population estimates.

## Licensing and attribution

The package maintainers identify their package as
[Open Data Commons PDDL 1.0](https://opendatacommons.org/licenses/pddl/1-0/), as shown
in their [pinned metadata](https://github.com/datasets/population/blob/d4b1a4a9a17e2123baf0ef119de05bceced1ab1b/datapackage.json)
and [pinned README](https://github.com/datasets/population/blob/d4b1a4a9a17e2123baf0ef119de05bceced1ab1b/README.md).
The World Bank's [indicator page](https://data.worldbank.org/indicator/SP.POP.TOTL)
identifies **CC BY 4.0**. Respect the underlying
[CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/)
and [World Bank additional terms](https://datacatalog.worldbank.org/public-licenses)
as well as the package license; the package's dedication is not presented as
replacing rights or attribution associated with upstream data.

Attribution: **World Bank, Population, total (SP.POP.TOTL)**. Underlying sources
include UN Population Division, national statistical offices, Eurostat and UN
Statistics Division. CSV packaging by datasets/population contributors. This
project copies the two CSV revisions without modification and produces derived
comparison results. No endorsement by these organizations is implied.
