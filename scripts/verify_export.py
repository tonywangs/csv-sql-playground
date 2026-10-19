"""Independent nested-loop oracle. Does not import application code.
Usage: python3 scripts/verify_export.py LEFT RIGHT OUTPUT MANIFEST
"""
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path


def verify(left_path, right_path, output_path, manifest_path):
    m = json.loads(Path(manifest_path).read_text())
    c = m['config']; tables = {}; headers = {}
    for side, path in [('left', left_path), ('right', right_path)]:
        raw = Path(path).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == m['sources'][side]['sha256'], side + ' source hash mismatch'
        assert len(raw) == m['sources'][side]['bytes']
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
        headers[side], tables[side] = rows[0], rows[1:]
        assert rows[0] == m['sources'][side]['headers']
    pairs = []; matched_right = set(); unmatched_left = []; match_count = 0
    for i, lrow in enumerate(tables['left'], 1):
        found = False
        for j, rrow in enumerate(tables['right'], 1):
            equal = all(lrow[a] != '' and rrow[b] != '' and lrow[a] == rrow[b] for a, b in zip(c['left_keys'], c['right_keys']))
            if equal:
                pairs.append([i, j]); matched_right.add(j); found = True; match_count += 1
        if not found:
            unmatched_left.append(i)
            if c['join'] in ('left', 'full'): pairs.append([i, None])
    unmatched_right = [j for j in range(1, len(tables['right']) + 1) if j not in matched_right]
    if c['join'] == 'full': pairs += [[None, j] for j in unmatched_right]
    assert pairs == m['pairs'], 'Source-row pairs differ'
    assert m['unmatched'] == {'left': unmatched_left, 'right': unmatched_right}
    keys = {s: [tuple(row[i] for i in c[s + '_keys']) for row in tables[s]] for s in tables}
    counters = {s: Counter(k for k in keys[s] if '' not in k) for s in tables}
    missing = {s: [i for i, k in enumerate(keys[s], 1) if '' in k] for s in tables}
    assert m['missing'] == missing
    counts = {'left_records': len(tables['left']), 'right_records': len(tables['right']), 'matched_pairs': match_count, 'expected_rows': len(pairs), 'unmatched_left': len(unmatched_left), 'unmatched_right': len(unmatched_right), 'missing_left': len(missing['left']), 'missing_right': len(missing['right']), 'duplicate_left_keys': sum(v > 1 for v in counters['left'].values()), 'duplicate_right_keys': sum(v > 1 for v in counters['right'].values()), 'many_to_many_keys': sum(v > 1 and counters['right'].get(k, 0) > 1 for k, v in counters['left'].items())}
    assert counts == m['counts'], 'Accounting differs'
    raw = Path(output_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == m['output']['sha256'], 'Output hash mismatch'
    assert len(raw) == m['output']['bytes'] and len(pairs) == m['output']['rows']
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True))
    expected_headers = ['_left_record', '_right_record'] + [s + '.' + headers[s][i] for s in ['left', 'right'] for i in c[s + '_columns']]
    assert rows[0] == expected_headers == m['output']['headers']
    expected = []
    for pair in pairs:
        values = ['' if i is None else str(i) for i in pair]
        for s, ordinal in zip(['left', 'right'], pair):
            values += ['' if ordinal is None else tables[s][ordinal - 1][i] for i in c[s + '_columns']]
        expected.append(values)
    assert rows[1:] == expected, 'Exported values differ'
    print(f'Verified every value and source-row pair: {len(pairs)} output records, {len(tables["left"])} + {len(tables["right"])} input records.')

if __name__ == '__main__':
    if len(sys.argv) != 5: raise SystemExit(__doc__)
    verify(*sys.argv[1:])
