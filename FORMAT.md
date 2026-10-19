# Files and coordinate contract

## `project.json` — `chart-point-desk/v1`

- `image`: original input `name`, byte-level `sha256`, decoded `width`, `height`.
- `calibration`: `null` for unfinished work, otherwise `x` and `y` axes. Each axis has `scale` (`linear` or `log10`) and exactly two `anchors`, each `{pixel, value}`. X pixels are horizontal columns; Y pixels are vertical rows. The other coordinate of a tick click is not used by the axis-aligned model.
- `series`: ordered `{id, name}` entries; IDs are unique and stable.
- `activeSeries`: ID used for new points.
- `points`: insertion-ordered `{id, series, px, py}` entries. IDs are unique. Moving points preserves order and identity; deleting and undoing restores them.

Each pixel lies in `[0, width)` or `[0, height)`. Inputs are JSON numbers, not numeric strings. Unknown fields are not used to compute values. Invalid required fields or unknown format versions are rejected before imported work replaces the current project. Project import does not interpret a filename as proof of identity: the user must supply image bytes whose SHA-256 and decoded dimensions match.

For an axis with anchors `(p₀,v₀)`, `(p₁,v₁)`, set `f(v)=v` for linear or `f(v)=log10(v)` for log. The application uses:

```
slope = (f(v₁) - f(v₀)) / (p₁ - p₀)
intercept = f(v₀) - slope * p₀
value = slope * pixel + intercept              # linear
value = 10 ** (slope * pixel + intercept)       # log10
```

Reversed directions require no flag: anchor ordering determines the slope. A source pixel is not a calibrated unit. The Y axis usually has a negative linear slope because image Y increases downward. The independent verifier uses endpoint interpolation and natural logarithms, rather than the application’s slope/intercept implementation.

## `points.csv`

UTF-8, comma-separated, RFC 4180-style quoting, CRLF row endings; embedded newlines in a quoted label are preserved. Header:

```
series,series_id,point_id,order,pixel_x,pixel_y,approximate_x,approximate_y
```

`order` is one-based within a series. The file itself follows global point insertion order. Numeric output uses JavaScript’s round-trippable number representation; this is serialization precision, not measurement accuracy. Series labels are exact, including punctuation; use a CSV parser, not string splitting. In spreadsheets import text columns as text to prevent formula interpretation.

## `manifest.json` — `chart-point-desk-manifest/v1`

Contains `approximate: true`, interpretation warning, `image`, `coordinateSystem`, `calibration`, `transformations`, `series`, and insertion-ordered `points` with `px`, `py`, and calculated `x`, `y`. `outputs` maps the generic download filenames to their SHA-256 hashes. Hash the downloaded bytes before newline conversion. Samples are renamed by chart in this repository; manifest output keys retain the original generic download names.

The manifest is an audit companion, not an editable project import. Use the separately hashed `project.json` for reopening. CSV is a reusable export, not an import format. Keep all three outputs and the unchanged original image. Manifest hashes detect changes relative to the manifest; they are not a digital signature or third-party authenticity claim.
