#!/usr/bin/env python3
"""Independent SQL oracle: no comparison-engine matching helpers used."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desk
ROOT=Path(__file__).resolve().parents[1]
def verify():
    paths=[ROOT/'demo/before.sqlite',ROOT/'demo/after.sqlite']
    hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    m=json.loads((ROOT/'demo/provenance.json').read_text())
    sql=sqlite3.connect(':memory:')
    for side,path in zip(('before','after'),paths):
        assert hashlib.sha256(path.read_bytes()).hexdigest()==m['snapshots'][side]['sqlite_sha256']
        sql.execute(f'ATTACH DATABASE ? AS {side}',(path.as_uri()+'?mode=ro&immutable=1',))
        for table,source in m['snapshots'][side]['sources'].items():
            raw=(ROOT/source['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==source['sha256']
            with (ROOT/source['path']).open(newline='',encoding='utf-8') as f:
                reader=csv.reader(f);header=next(reader);rows=list(reader)
            actual=sql.execute(f'SELECT * FROM {side}.{table}').fetchall()
            assert actual==[tuple(row) for row in rows],f'Import mismatch {side}.{table}'
    r=desk.compare(*(desk.snapshot(p) for p in paths),{'countries':['id'],'regions':['id']})
    results={}
    for table in ('countries','regions'):
        cols=[r[1] for r in sql.execute(f'PRAGMA before.table_info({table})')]
        eq=' AND '.join(f'a."{c}" IS b."{c}"' for c in cols)
        for side in ('before','after'):
            assert sql.execute(f'SELECT count(*)=count(DISTINCT id) AND count(*)=count(id) FROM {side}.{table}').fetchone()[0]
        counts={
          'added':sql.execute(f'SELECT count(*) FROM after.{table} b WHERE NOT EXISTS(SELECT 1 FROM before.{table} a WHERE a.id=b.id)').fetchone()[0],
          'removed':sql.execute(f'SELECT count(*) FROM before.{table} a WHERE NOT EXISTS(SELECT 1 FROM after.{table} b WHERE a.id=b.id)').fetchone()[0],
          'changed':sql.execute(f'SELECT count(*) FROM before.{table} a JOIN after.{table} b ON a.id=b.id WHERE NOT ({eq})').fetchone()[0],
          'unchanged':sql.execute(f'SELECT count(*) FROM before.{table} a JOIN after.{table} b ON a.id=b.id WHERE {eq}').fetchone()[0],
          'ambiguous_before':0,'ambiguous_after':0}
        assert counts==r['tables'][table]['counts'],(counts,r['tables'][table]['counts'])
        # Independently compare actual IDs in each category, not just aggregate counts.
        for kind in ('added','removed','changed','unchanged'):
            if kind=='added':query=f'SELECT b.id FROM after.{table} b WHERE NOT EXISTS(SELECT 1 FROM before.{table} a WHERE a.id=b.id)'
            elif kind=='removed':query=f'SELECT a.id FROM before.{table} a WHERE NOT EXISTS(SELECT 1 FROM after.{table} b WHERE a.id=b.id)'
            else:query=f'SELECT a.id FROM before.{table} a JOIN after.{table} b ON a.id=b.id WHERE '+('NOT ' if kind=='changed' else '')+f'({eq})'
            expected={row[0] for row in sql.execute(query)}
            actual={(record['after'] or record['before'])[0]['values'][cols.index('id')][1] for record in r['tables'][table]['records'] if record['kind']==kind}
            assert expected==actual
        results[table]=counts
    sql.close()
    assert hashes==[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    print(json.dumps({'oracle':'independent SQL joins + exact CSV import + SHA-256 preservation','counts':results},indent=2))
    return results
if __name__=='__main__':verify()
