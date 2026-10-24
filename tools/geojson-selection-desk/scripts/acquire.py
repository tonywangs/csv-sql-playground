import urllib.request,json,hashlib,pathlib
root=pathlib.Path(__file__).resolve().parents[1]/'data'
rev='f1890d9f152c896d250a77557a5751a93d494776'
base=f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{rev}/'
records={}
for name,path in [('countries.source.json','geojson/ne_110m_admin_0_countries.geojson'),('LICENSE-natural-earth.md','LICENSE.md')]:
    b=urllib.request.urlopen(base+path).read(); (root/name).write_bytes(b)
    records[name]={'url':base+path,'sha256':hashlib.sha256(b).hexdigest()}
a=json.loads((root/'countries.source.json').read_bytes()); assert a.pop('crs')['properties']['name']=='urn:ogc:def:crs:OGC:1.3:CRS84'
b=(json.dumps(a,ensure_ascii=False,separators=(',',':'))+'\n').encode();(root/'countries.geojson').write_bytes(b)
records['countries.geojson']={'sha256':hashlib.sha256(b).hexdigest(),'conversion':'Remove legacy CRS84 declaration only; serialize JSON, no coordinate transformation.'}
(root/'provenance.json').write_text(json.dumps({'revision':rev,'license':'Natural Earth public domain; see LICENSE-natural-earth.md','files':records},indent=2)+'\n')
print('Acquired',len(a['features']),'features')
