"""Replay independently recorded Calc oracle against current implementation."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import inspect
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'results/libreoffice.json').read_text())
assert 'LibreOffice' in manifest['oracle']
for r in manifest['results']:
    m=inspect((ROOT/'fixtures'/r['workbook']).read_bytes(),r['workbook'])
    assert m['source']['sha256']==r['sha256']
    supported={c['id'] for c in m['cells'].values() if c['coverage'] in ('supported','partial')}
    assert supported==set(r['precedents'])
    assert not r['mismatches']
    for c,expected in r['precedents'].items():
        actual={e['target'] for e in m['edges'] if e['source']==c}
        assert (set(expected)==actual if m['cells'][c]['coverage']=='supported' else actual.issubset(set(expected))),(r['workbook'],c)
    print(r['workbook'],len(supported),'supported/partial formulas match independent Calc manifest')
