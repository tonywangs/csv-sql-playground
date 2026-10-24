# Crosscut

Tools for inspecting, joining, querying, and understanding data.


Independent utilities collected into one private repository. Each lives under `tools/<name>/`; run its installation and commands from that directory. This is a source consolidation, not a unified application.

Original repositories and server workspaces were retained. Original histories are reachable through merge commits and `history/` tags. Unpublished source was copied from the server; it may be incomplete.

- [csv-reconcile-desk](tools/csv-reconcile-desk/README.md): An offline CSV reconciliation tool with a browsable comparison report that preserves duplicate records and exposes ambiguous matches.
- [csv-pivot-desk](tools/csv-pivot-desk/README.md): A local CSV analysis workbench for building pivot tables, inspecting contributing records, and exporting reproducible summaries with explicit missing-value handling.
- [csv-join-desk](tools/csv-join-desk/README.md): A local CSV joining workbench that previews unmatched keys and row multiplication before exporting traceable combined tables.
- [sqlite-snapshot-desk](tools/sqlite-snapshot-desk/README.md): An offline SQLite comparison application for inspecting schema and record changes between database snapshots, with explicit row identity and complete accounting.
- [sqlite-query-desk](tools/sqlite-query-desk/README.md): A local SQLite query workbench for exploring tables, saving parameterized queries, and exporting reproducible results with explicit execution limits.
- [jsonl-selection-desk](tools/jsonl-selection-desk/README.md): A local JSONL workbench for inspecting nested records, filtering by typed values, and exporting traceable subsets without rewriting source records.
- [json-schema-review-desk](tools/json-schema-review-desk/README.md): A local JSON validation workbench linking validation failures to source values and schema rules, with portable review reports.
- [spreadsheet-formula-map](tools/spreadsheet-formula-map/README.md): A local spreadsheet explorer for tracing formula dependencies, inspecting source cells, and saving portable review reports with explicit coverage limits.
- [chart-point-desk](tools/chart-point-desk/README.md): An offline chart-digitizing workbench for calibrating plot images, marking data points, and exporting approximate values with inspectable source coordinates.
- [geojson-selection-desk](tools/geojson-selection-desk/README.md): An offline map workbench for inspecting GeoJSON features, selecting useful subsets, and exporting unchanged geometries with traceable selection records.
