#!/usr/bin/env python3
"""Reacquire pinned public data and license; refuse hash changes."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
ROOT = Path(__file__).resolve().parents[1]
metadata = json.loads((ROOT / 'data/source.json').read_text())
for entry in metadata['files']:
    with urlopen(entry['url'], timeout=30) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    assert hashlib.sha256(raw).hexdigest() == entry['sha256'], 'Source hash changed'
    (ROOT / 'data' / entry['name']).write_bytes(raw)
    print(entry['name'], entry['sha256'])
