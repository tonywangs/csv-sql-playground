"""Fetch pinned upstream demo bytes and verify against the committed manifest."""
import hashlib,json,pathlib,urllib.request
root=pathlib.Path(__file__).resolve().parents[1]/'public/demo'
m=json.loads((root/'sources.json').read_text())
for item in m['files']:
    b=urllib.request.urlopen(item['url'],timeout=30).read(1048577)
    assert len(b)<=1048576 and hashlib.sha256(b).hexdigest()==item['sha256'],item['name']
    (root/item['name']).write_bytes(b)
    print('verified',item['name'],len(b))
