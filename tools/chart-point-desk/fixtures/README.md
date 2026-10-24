# Published inputs and frozen evaluation

Two **published charts**, not locally invented plots, were obtained from Our World in Data on the UTC date recorded in `owid/provenance.json`:

| Chart | Published chart and selection | Underlying data subset |
|---|---|---|
| Population | [World, 1950–2023](https://ourworldindata.org/grapher/population?tab=chart&country=~OWID_WRL&time=1950..2023) | World population, annual values, UN WPP 2024 via OWID |
| Life expectancy | [World, 1950–2023](https://ourworldindata.org/grapher/life-expectancy?tab=chart&country=~OWID_WRL&time=1950..2023) | World period life expectancy at birth, annual values, UN WPP 2024 via OWID |

Attribution: **Our World in Data; United Nations, Department of Economic and Social Affairs, Population Division (2024). World Population Prospects 2024, Online Edition.** The original chart footers additionally identify sources in the publishers’ full long-run series. Only World 1950–2023 is used here. OWID’s indicator metadata describes the source combination; post-1950 life expectancy and World population use the UN source. Population’s 1950 transition is not one of the selected reference years.

## License evidence and revisions

- Each unchanged publisher SVG contains its visible **CC BY** attribution and hyperlink to [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This is preserved in the rendered PNGs.
- `owid/*.indicator.json` preserves the publisher’s metadata, including `origins` entries for the United Nations with **CC BY 3.0 IGO** licensing and source links. See also the UN’s [data portal API license](https://population.un.org/dataportalapi/index.html) and [WPP data sources publication](https://population.un.org/wpp/assets/Excel%20Files/4_Metadata/WPP2024_Data_Sources.pdf). This attribution does not assert licensing of unrelated periods or providers.
- `owid/provenance.json` records retrieval UTC time, all original image/data/metadata URLs, byte counts and SHA-256 hashes, and indicator revision identifiers, update times, dataset versions, and source checksums. The exact CSVs and metadata used are included, even if upstream files later change.
- `owid/rasterization.json` records the browser version, image dimensions, input/output hashes, and rasterization method. Original SVG/CSV files are unchanged. PNGs are **uncropped rasterizations at 850 × 600 pixels**, using Chromium SVG-as-image rendering, a white background and device scale 1. External fonts/resources are disabled; fallback system fonts can affect text rendering. The plotted geometry is not re-created from the CSV.

## Reproducible acquisition

From the repository root, use an empty output directory:

```sh
python3 scripts/acquire.py --output /tmp/chart-point-public-inputs
```

This performs ordinary unauthenticated GETs to the exact chart/data/metadata URLs encoded in the script and recorded in provenance. It refuses to overwrite a nonempty directory. OWID endpoints are live: compare fresh hashes with the frozen provenance before assuming identical revisions. A changed upstream export is new input, not a reason to silently replace this benchmark. The tracked source snapshots make the existing experiment reproducible without network access.

After installing the pinned Playwright dependency/browser:

```sh
node scripts/rasterize.mjs /tmp/chart-point-rasters
```

The rasterizer uses the tracked original SVGs, blocks external resources, and saves its own provenance. Cross-platform font/browser changes may change PNG hashes, so the application samples intentionally reconnect only to the tracked PNGs. Inspect the new rasters separately if they differ.

## Evaluation protocol

`reference-plan.json` freezes five reference years for each chart, source values, matching by insertion order, calibration anchors, pixel-derived absolute tolerances, source hashes, and a UTC freeze timestamp. Its SHA-256 is in `reference-plan.sha256`. `scripts/freeze-reference.py` documents the one-time preparation and refuses to overwrite an existing plan. It ran before raster point selection and evaluation.

`selections.json` contains the manually read raster point coordinates. The visual reading was performed by this implementation run, not a blinded human trial. No y coordinates were back-projected from numerical reference data or taken from SVG line paths. The browser test then adds these coordinates through actual canvas interactions and exports the resulting data. Replaying fixed selections tests workflow and transformations; it is not another independent operator trial.

The Python verifier separately parses the exported CSV and checks each point against the original source CSV and frozen matching rules. All errors and the single tolerance failure remain in [the results](../results/accuracy.md). Linear, logarithmic, reversed, and invalid-calibration synthetic controls are clearly identified separately. No random sampling or random experimental seed is involved; runtime point UUIDs identify points but do not affect coordinates or results.
