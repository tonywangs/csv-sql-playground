#!/usr/bin/env python3
"""Compare all returned cells/multiplicities against CSV-only Python calculations.
The oracle does not execute SQL or read the generated SQLite database.
"""
import collections, csv, hashlib, io, json, sys, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from desk.core import bundle, execute, sha

def expected():
    with (ROOT/'demo/raw/countries.csv').open(newline='') as f: countries=list(csv.DictReader(f))
    with (ROOT/'demo/raw/regions.csv').open(newline='') as f: regions=list(csv.DictReader(f))
    groups=collections.defaultdict(list)
    for row in regions:groups[row['iso_country']].append(row)
    ranked=sorted([[c['code'],c['name'],len(groups[c['code']])] for c in countries],key=lambda r:(-r[2],r[0]))
    filtered=sorted([[c['name'],r['code'],r['name']] for c in countries if c['code']=='CA' for r in groups[c['code']]],key=lambda r:r[1])
    continents=collections.defaultdict(lambda:[set(),0])
    for c in countries:
        continents[c['continent']][0].add(c['code'])
        continents[c['continent']][1]+=len(groups[c['code']])
    summary=[[k,len(v[0]),v[1]] for k,v in sorted(continents.items())]
    return [ranked,filtered,summary]

def typed(rows):return [[{'type':'integer' if type(v) is int else 'text','value':str(v) if type(v) is int else v} for v in row] for row in rows]

def verify_archive(path, rows=None, query=None, status="complete"):
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist())=={'manifest.json','results.json','results.csv'}
        m=json.loads(z.read('manifest.json')); r=json.loads(z.read('results.json'))
        for name,digest in m['output_hashes'].items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
        for k,v in r.items():
            if k not in ('format','rows'):assert m[k]==v,(path,k)
        assert r['row_count']==len(r['rows'])
        assert r['source']['sha256']==hashlib.sha256((ROOT/'demo/ourairports.sqlite').read_bytes()).hexdigest()
        assert r['source_unchanged']
        if rows is not None:
            assert r['status']==status
            if status != 'complete': assert m['partial_acknowledged']
            assert r['rows']==typed(rows), f'Independent oracle differs: {path}'
        if query:
            assert r['sql']==query['sql'] and r['parameters']==query['parameters']
        csv_rows=list(csv.reader(io.StringIO(z.read('results.csv').decode(),newline='')))
        assert csv_rows[0]==r['columns']
        assert csv_rows[1:]==[[c['value'] if c['value'] is not None else '' for c in row] for row in r['rows']]
        return {'archive':str(path.relative_to(ROOT)),'rows':len(r['rows']),'status':r['status'],'all_cells_and_multiplicities_match':rows is not None,'output_hashes_verified':True}

def main():
    provenance=json.loads((ROOT/'demo/provenance.json').read_text())
    for name,metadata in provenance['files'].items():assert sha((ROOT/'demo/raw'/name).read_bytes())==metadata['sha256']
    database=ROOT/'demo/ourairports.sqlite'
    before=database.read_bytes()
    queries=json.loads((ROOT/'demo/queries.json').read_text())
    source={'name':'OurAirports countries + regions','sha256':sha(before),'bytes':len(before)}
    evidence=[]
    for i,(q,rows) in enumerate(zip(queries,expected())):
        r=execute(database,dict(q,source=source,settings={'rows':10000,'bytes':1048576,'seconds':3}))
        assert r['rows']==typed(rows) and r['status']=='complete',q['name']
        path=ROOT/f'results/demo-{i+1}.zip'
        if '--record' in sys.argv:path.write_bytes(bundle(r))
        evidence.append(verify_archive(path,rows,q))
    browser=ROOT/'results/browser-real-data.zip'
    evidence.append(verify_archive(browser,expected()[1],queries[1]))
    evidence.append(verify_archive(ROOT/'results/browser-partial.zip',expected()[1][:2],queries[1],status='truncated'))
    assert database.read_bytes()==before
    out={'oracle':'Python csv + dictionaries + sorting; no SQLite in expected-value implementation','source_sha256_before':sha(before),'source_sha256_after':sha(database.read_bytes()),'queries':evidence}
    if '--record' in sys.argv:(ROOT/'results/independent-verification.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
