"""Verify retained source bytes, or reacquire exact pinned public revisions."""
import argparse, hashlib, json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');args=p.parse_args()
manifest=json.loads((ROOT/'fixtures/sources.json').read_text())
for item in manifest['files']:
    path=ROOT/'fixtures'/item['file']
    data=urllib.request.urlopen(item['url'],timeout=60).read() if args.download else path.read_bytes()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],item['file']+' source mismatch'
    if args.download:path.write_bytes(data)
    print(item['file'],item['sha256'],'verified')
