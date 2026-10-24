"""Reproduce a bounded, unmodified-row subset of pinned OurAirports CSVs."""
import csv, hashlib, io, json, pathlib, urllib.request
ROOT = pathlib.Path(__file__).resolve().parents[1]
REV = 'b529623d2a0b09a9be78d37fc7a7a5e1e16e3451'
BASE = f'https://raw.githubusercontent.com/davidmegginson/ourairports-data/{REV}/'
def main():
    metadata = {'revision': REV, 'selection': 'First 300 large_airport records in upstream order; all countries. All columns retained.', 'sources': {}}
    for name in ['airports.csv', 'countries.csv', 'LICENSE']:
        raw = urllib.request.urlopen(BASE + name, timeout=60).read()
        item = {'url': BASE + name, 'upstream_sha256': hashlib.sha256(raw).hexdigest(), 'upstream_bytes': len(raw)}
        if name.endswith('.csv'):
            rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
            selected = rows[1:] if name == 'countries.csv' else [r for r in rows[1:] if r[rows[0].index('type')] == 'large_airport'][:300]
            out = io.StringIO(newline=''); csv.writer(out).writerows([rows[0], *selected]); content = out.getvalue().encode()
            item.update(rows=len(selected), subset_sha256=hashlib.sha256(content).hexdigest(), upstream_record_ordinals=[i for i, r in enumerate(rows[1:], 1) if name == 'countries.csv' or r in selected])
        else:
            content = raw
        (ROOT / 'data' / name).write_bytes(content)
        metadata['sources'][name] = item
    (ROOT / 'data' / 'provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Acquired pinned real demo:', {n: x.get('rows') for n, x in metadata['sources'].items()})
if __name__ == '__main__': main()
