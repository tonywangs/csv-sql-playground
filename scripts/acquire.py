"""Acquire public OWID chart exports and metadata. Never overwrites frozen fixtures."""
import argparse, datetime, hashlib, json, pathlib, urllib.request, re
p=argparse.ArgumentParser(); p.add_argument('--output',required=True); args=p.parse_args()
out=pathlib.Path(args.output); out.mkdir(parents=True,exist_ok=True)
if any(out.iterdir()): raise SystemExit('Output must be empty; frozen fixtures must not be overwritten.')
records=[]
def get(url, name):
    req=urllib.request.Request(url,headers={'User-Agent':'ChartPointDesk reproducible acquisition/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r: data=r.read()
    (out/name).write_bytes(data)
    records.append({'file':name,'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    return data
charts=[]
for slug in ['population','life-expectancy']:
    base='https://ourworldindata.org/grapher/'+slug
    query='?tab=chart&country=~OWID_WRL&time=1950..2023'
    get(base+'.svg'+query,slug+'.svg')
    get(base+'.csv'+query+'&csvType=filtered',slug+'.csv')
    meta=json.loads(get(base+'.metadata.json'+query+'&csvType=filtered',slug+'.metadata.json'))
    column=next(iter(meta['columns'].values()))
    full=json.loads(get(column['fullMetadata'],slug+'.indicator.json'))
    charts.append({'id':slug,'page':base+query,'title':meta['chart']['title'],'entity':'World','years':[1950,2023],
      'revision':{k:full.get(k) for k in ['id','updatedAt','datasetVersion','dataChecksum','metadataChecksum']},
      'chart_license':'CC BY 4.0','chart_license_url':'https://creativecommons.org/licenses/by/4.0/',
      'data_license':'CC BY 3.0 IGO (UN WPP 2024, the World 1950–2023 subset only)',
      'data_license_evidence':slug+'.indicator.json: origins[].license for United Nations',
      'attribution':'Our World in Data; United Nations, Department of Economic and Social Affairs, Population Division (2024). World Population Prospects 2024, Online Edition.',
      'processing':'Original downloaded SVG and CSV bytes unchanged. PNG rasterization documented in rasterization.json. No cropping.'})
(out/'provenance.json').write_text(json.dumps({'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'charts':charts,'files':records},indent=2)+'\n')
print('Acquired',len(records),'public source files into',out)
