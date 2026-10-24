#!/usr/bin/env python3
"""Rebuild the demo offline, optionally reacquire pinned source bytes."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'demo'
REVISIONS = {'before': 'ce94208f0918987f3594a1afd8409e5146d5aff4', 'after': 'e6e15e5a5b8add6d6b1447ca453a1136103585e4'}
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def build(fetch=False):
    manifest = json.loads((DEMO/'provenance.json').read_text())
    for side, revision in REVISIONS.items():
        target = DEMO / (side+'.sqlite')
        temp = DEMO / (side+'.building.sqlite')
        temp.unlink(missing_ok=True)
        db = sqlite3.connect(temp)
        for table in ('countries', 'regions'):
            entry = manifest['snapshots'][side]['sources'][table]
            source = ROOT / entry['path']
            if fetch:
                data = urllib.request.urlopen(entry['url'], timeout=30).read()
                if hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise ValueError('Downloaded source hash mismatch')
                source.write_bytes(data)
            assert sha(source) == entry['sha256'], source
            with source.open(newline='',encoding='utf-8') as file:
                rows = csv.reader(file)
                columns = next(rows)
                db.execute('CREATE TABLE '+table+' ('+', '.join('"'+c+'" TEXT' for c in columns)+')')
                db.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in columns)+')', rows)
        db.commit(); db.close()
        temp.replace(target)
        print(side, sha(target))
        expected = manifest['snapshots'][side].get('sqlite_sha256')
        if expected and sha(target) != expected:
            raise ValueError('SQLite bytes differ; check SQLite version. Source-level oracle remains authoritative.')
if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--fetch',action='store_true')
    build(parser.parse_args().fetch)
