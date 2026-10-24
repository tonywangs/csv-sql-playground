"""Independent export comparison: Python JSON parser, no application imports."""
import json,hashlib,sys,pathlib
source,output,manifest=map(pathlib.Path,sys.argv[1:])
s=json.loads(source.read_bytes());o=json.loads(output.read_bytes());m=json.loads(manifest.read_bytes())
assert hashlib.sha256(source.read_bytes()).hexdigest()==m['sourceHash']
assert hashlib.sha256(output.read_bytes()).hexdigest()==m['outputHash']
inc=m['sourceOrdinals'];exc=m['excluded'];uns=[x['ordinal'] for x in m['unsupported']]
assert len(inc)==len(set(inc)) and inc==sorted(inc)
assert sorted(inc+exc+uns)==list(range(len(s['features'])))
assert m['sourceCount']==len(s['features'])
assert o['type']=='FeatureCollection' and 'bbox' not in o
assert o['features']==[s['features'][i] for i in inc]
print(f'Independently verified {len(inc)} included, {len(exc)} excluded, {len(uns)} unsupported; all source features reconciled.')
