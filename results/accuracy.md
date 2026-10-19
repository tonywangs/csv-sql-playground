# Real-chart digitization error

Ten manually selected points from two published Our World in Data charts, World 1950–2023. Source: UN World Population Prospects 2024, processed by OWID. These are digitized estimates, not original measurements.

The reference years, one-to-one insertion-order matching, calibration, and tolerances were frozen in `fixtures/reference-plan.json` before selections and evaluation. `fixtures/selections.json` records visual raster readings, not coordinates calculated from reference values.

Independent verification uses Python’s CSV parser and endpoint interpolation, separately from the JavaScript application. Every selected point is reported below; no outliers were excluded.

## population

Absolute tolerances: X ≤ 0.208768 years; Y ≤ 55427251.7. X uses 2 source pixels and Y uses 3. Population Y units are people; life-expectancy Y units are years.

| Reference year | Source value | Selected pixels | Approx. X | Approx. Y | Signed X error | Signed Y error | Pass |
|---:|---:|:---|---:|---:|---:|---:|:---|
| 1960 | 3015470889 | 164, 348 | 1960 | 3030023095 | 0 | 14552205.7 | yes |
| 1980 | 4447606240 | 356, 269 | 1980.04175 | 4489607390 | 0.0417537 | 42001150.3 | yes |
| 2000 | 6171702992 | 547, 179 | 1999.97912 | 6152424942 | -0.0208768 | -19278049.7 | yes |
| 2020 | 7887001289 | 739, 88 | 2020.02088 | 7833718245 | 0.0208768 | -53283044.2 | yes |
| 2023 | 8091734933 | 768, 74 | 2023.04802 | 8092378753 | 0.0480167 | 643819.887 | yes |

Maximum absolute Y error: 53283044.2; mean absolute Y error: 25951654; Y RMSE: 32208706.3.

## life-expectancy

Absolute tolerances: X ≤ 0.209644 years; Y ≤ 0.568720379. X uses 2 source pixels and Y uses 3. Population Y units are people; life-expectancy Y units are years.

| Reference year | Source value | Selected pixels | Approx. X | Approx. Y | Signed X error | Signed Y error | Pass |
|---:|---:|:---|---:|---:|---:|---:|:---|
| 1960 | 47.8198 | 167, 280 | 1960 | 47.77251185 | 0 | -0.0472881517 | yes |
| 1980 | 60.502 | 358, 215 | 1980.02096 | 60.09478673 | 0.0209644 | -0.40721327 | yes |
| 2000 | 66.4333 | 548, 185 | 1999.93711 | 65.78199052 | -0.0628931 | -0.651309479 | NO |
| 2020 | 71.9166 | 739, 152 | 2019.95807 | 72.03791469 | -0.0419287 | 0.121314692 | yes |
| 2023 | 73.1694 | 768, 146 | 2022.9979 | 73.17535545 | -0.00209644 | 0.00595545024 | yes |

Maximum absolute Y error: 0.651309479; mean absolute Y error: 0.246616209; Y RMSE: 0.348429498.

## Limits

Failed tolerances: 1 / 10. Exact per-point values and labeled synthetic controls are in `accuracy.json`.

Only two clean linear, axis-aligned charts and one set of manual selections were measured. Both charts use the same publisher and related data source. Logarithmic and reversed axes are supported and checked with labeled synthetic controls; this is not a real-chart accuracy study of those cases. No repeated-operator study or statistical confidence interval was performed.

The chosen tolerance budgets represent pixel placement and calibration reading sensitivity, not uncertainty in the underlying demographic estimates. Rasterization used browser fallback fonts without cropping; source SVGs and numerical CSVs remain unchanged. Interpolation between years, anchor rounding, raster line width, and operator judgment can all affect results. Do not treat these figures as scientific validation of the source data.

Verification checks reproducibility, hashes, independent transforms, and the complete recorded result (including the miss). Add `--require-tolerances` for a strict experimental gate; it exits 1 for this frozen result.

Reproduce: `python3 scripts/verify.py` (frozen sample exports) or, after the browser test, `python3 scripts/verify.py --exports test-results/exports` (fresh browser exports).
