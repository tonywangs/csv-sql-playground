# Reproducible verification

Core checks need only Python 3.10+:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/demo.py
```

The demo independently checks pinned hashes and runs `scripts/verify_population.py`.
That verifier uses SQLite joins with unique-key constraints instead of the
application's grouping algorithm. It checks every source reference, value, field
difference, event classification and accounting total, not just expected totals.
It is specific to the bundled unique-key population revisions. Duplicate behavior
is covered by controlled tests and seeded randomized multiset/conservation checks.

## Installation smoke check

Install using the README instructions, then run the installed command from a
directory **outside** this checkout to confirm package data and entry points work:

```sh
/path/to/.venv/bin/csv-reconcile /path/to/csv-reconcile-desk/data/population/before.csv \
  /path/to/csv-reconcile-desk/data/population/after.csv \
  --key 'Country Code' --key Year --json /tmp/installed.json --html /tmp/installed.html
python3 scripts/verify_population.py /tmp/installed.json
```

## Optional browser checks

These require Node.js and a downloaded Chromium browser, only for testing.
The application and its generated reports have no Node.js dependency.
On Linux/macOS, keep the test dependencies outside the repository:

```sh
npm install --cache /tmp/csv-npm-cache --prefix /tmp/csv-report-browser playwright@1.58.2
PLAYWRIGHT_BROWSERS_PATH=/tmp/csv-playwright-browsers /tmp/csv-report-browser/node_modules/.bin/playwright install chromium
python3 scripts/demo.py
PLAYWRIGHT_BROWSERS_PATH=/tmp/csv-playwright-browsers \
PLAYWRIGHT_MODULE=/tmp/csv-report-browser/node_modules/playwright \
node scripts/check_browser.cjs
```

Chromium requires its usual system libraries. On hosts without them, install the
OS prerequisites using your normal administrator workflow. `PYTHON` can override
the Python executable used by the browser checks. An optional first script
argument saves a screenshot. The test uses an offline browser context and local
`file://` navigation, exercises all status filters, paging, search, expanded row
references, mobile width, duplicate/missing-key presentation, multiline values and
HTML-injection payloads. It fails on JavaScript errors or external requests.
