#!/usr/bin/env python3
"""Recreate the SQLite conversion from hash-verified, revision-pinned CSV."""
import csv, hashlib, json, sqlite3, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
REV = 'b529623d2a0b09a9be78d37fc7a7a5e1e16e3451'
def main():
    manifest_path = ROOT / 'demo/provenance.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    files = {}
    for name in ('countries.csv', 'regions.csv', 'SOURCE-README.md'):
        url = f'https://raw.githubusercontent.com/davidmegginson/ourairports-data/{REV}/' + ('README.md' if name == 'SOURCE-README.md' else name)
        path = ROOT / 'demo/raw' / name
        if '--fetch' in sys.argv:
            data = urllib.request.urlopen(url, timeout=30).read(2_000_000)
            if manifest and hashlib.sha256(data).hexdigest() != manifest['files'][name]['sha256']:
                raise ValueError('Upstream hash mismatch: ' + name)
            path.write_bytes(data)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest: assert digest == manifest['files'][name]['sha256'], name
        files[name] = {'url': url, 'sha256': digest, 'bytes': path.stat().st_size}
    target = Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else ROOT / 'demo/ourairports.sqlite'
    target.unlink(missing_ok=True)
    con = sqlite3.connect(target)
    counts = {}
    for table in ('countries', 'regions'):
        with (ROOT / f'demo/raw/{table}.csv').open(newline='') as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            con.execute('CREATE TABLE ' + table + '(' + ','.join('"'+c+'" '+('INTEGER' if c == 'id' else 'TEXT') for c in cols) + ')')
            rows = [[int(r[c]) if c == 'id' else r[c] for c in cols] for r in reader]
            con.executemany('INSERT INTO ' + table + ' VALUES ('+','.join('?' for _ in cols)+')', rows)
            counts[table] = len(rows)
    con.commit()
    con.close()
    if not manifest:
        manifest_path.write_text(json.dumps({'source':'OurAirports', 'revision':REV, 'acquired_utc':'2026-10-19', 'license':'Public Domain', 'license_url':'https://ourairports.com/data/', 'license_evidence':'license-evidence.txt', 'conversion':'CSV id fields become INTEGER; all other fields remain TEXT, including empty strings. Source order retained. No filtering.', 'files':files, 'rows':counts}, indent=2)+'\n')
    print(json.dumps({'rows':counts, 'database_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
if __name__ == '__main__': main()
