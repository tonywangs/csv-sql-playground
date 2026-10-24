import pathlib,json,hashlib,subprocess
root=pathlib.Path(__file__).resolve().parents[1]
p=json.loads((root/'data/provenance.json').read_text())
for name,item in p['files'].items():assert hashlib.sha256((root/'data'/name).read_bytes()).hexdigest()==item['sha256'],name
original=json.loads((root/'data/countries.source.json').read_bytes());converted=json.loads((root/'data/countries.geojson').read_bytes());original.pop('crs');assert original==converted
files=[p for p in root.rglob('*') if p.is_file() and not any(x in p.relative_to(root).parts for x in ['.git','node_modules','test-results','.agents','.codex'])]
assert len(files)<=1000 and sum(x.stat().st_size for x in files)<=32*1024*1024
assert all(x.stat().st_size<=10*1024*1024 for x in files)
assert all(x.suffix!='.log' or x.relative_to(root).as_posix()=='results/tests.log' for x in files)
print(f'Provenance, conversion and package limits verified: {len(files)} files, {sum(x.stat().st_size for x in files)} bytes.')
