"""Independent Calc precedent queries; requires LibreOffice + matching Python UNO.
Run with .venv/bin/python scripts/verify_libreoffice.py; SOFFICE may override executable.
Only public fixture files are opened, read-only, without macro execution or link updates.
"""
import sys, os, json, time, subprocess, tempfile, socket, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try: import uno
except ImportError:
    sys.path.append('/usr/lib/python3/dist-packages')
    import uno
from engine import inspect
ROOT=Path(__file__).resolve().parents[1]
def prop(k,v):
    p=uno.createUnoStruct('com.sun.star.beans.PropertyValue');p.Name=k;p.Value=v;return p

def main():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='formula-calc-') as profile:
        process=subprocess.Popen([os.environ.get('SOFFICE','libreoffice'),'--headless','--norestore','--nodefault','--nofirststartwizard','-env:UserInstallation='+Path(profile).as_uri(),f'--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext'],stdout=subprocess.DEVNULL,stderr=None,env=dict(os.environ))
        try:
            local=uno.getComponentContext();resolver=local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',local)
            for attempt in range(100):
                try: ctx=resolver.resolve(f'uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext');break
                except Exception:
                    if process.poll() is not None: raise RuntimeError('LibreOffice exited before UNO connection')
                    time.sleep(.1)
            else: raise RuntimeError('LibreOffice did not accept UNO connection')
            desktop=ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',ctx)
            results=[]
            for path in sorted((ROOT/'fixtures').glob('*.xlsx')):
                data=path.read_bytes();model=inspect(data,path.name)
                doc=desktop.loadComponentFromURL(path.as_uri(),'_blank',0,(prop('Hidden',True),prop('ReadOnly',True),prop('UpdateDocMode',0),prop('MacroExecutionMode',4)))
                if doc is None: raise RuntimeError('Calc could not load '+path.name)
                sheets=doc.getSheets(); names=list(sheets.getElementNames()); expected={}
                def query(c,recursive=False):
                    cell=sheets.getByName(c['sheet']).getCellRangeByName(c['address'])
                    ranges=cell.queryPrecedents(recursive).getRangeAddresses();out=set()
                    for r in ranges:
                        for row in range(r.StartRow,r.EndRow+1):
                            for col in range(r.StartColumn,r.EndColumn+1):
                                # No value reads or calculation results are used.
                                # Keep address construction independent from engine key/coordinate helpers.
                                letters='';n=col+1
                                while n:n,d=divmod(n-1,26);letters=chr(65+d)+letters
                                out.add("'"+names[r.Sheet].replace("'","''")+"'!"+letters+str(row+1))
                    out.discard(c['id']) # Calc includes the starting range itself.
                    return out
                def token_references(c):
                    cell=sheets.getByName(c['sheet']).getCellRangeByName(c['address'])
                    origin=cell.getCellAddress()
                    out=set()
                    def absolute(r):
                        if r.Flags & (2|8|32): return None
                        return (origin.Sheet+r.RelativeSheet if r.Flags & 16 else r.Sheet,
                                origin.Column+r.RelativeColumn if r.Flags & 1 else r.Column,
                                origin.Row+r.RelativeRow if r.Flags & 4 else r.Row)
                    def add(s,col,row):
                        letters='';n=col+1
                        while n:n,d=divmod(n-1,26);letters=chr(65+d)+letters
                        out.add("'"+names[s].replace("'","''")+"'!"+letters+str(row+1))
                    for t in cell.getTokens():
                        d=t.Data
                        if getattr(d,'typeName','')=='com.sun.star.sheet.SingleReference':
                            a=absolute(d)
                            if a is not None:add(*a)
                        elif getattr(d,'typeName','')=='com.sun.star.sheet.ComplexReference':
                            a=absolute(d.Reference1);b=absolute(d.Reference2)
                            if a is None or b is None:continue
                            s1,c1,r1=a;s2,c2,r2=b
                            for si in range(min(s1,s2),max(s1,s2)+1):
                                for col in range(min(c1,c2),max(c1,c2)+1):
                                    for row in range(min(r1,r2),max(r1,r2)+1):add(si,col,row)
                    return out
                mismatches=[];query_mismatches=[];edge_count=0;manifest={}; examples=[]
                for c in model['cells'].values():
                    if c['coverage'] not in ('supported','partial'):continue
                    actual={e['target'] for e in model['edges'] if e['source']==c['id']}
                    oracle=token_references(c); inspected=query(c); manifest[c['id']]=sorted(oracle);edge_count+=len(actual)
                    if actual!=inspected:query_mismatches.append({'cell':c['id'],'formula':c['formula'],'only_map':sorted(actual-inspected),'only_calc_query':sorted(inspected-actual)})
                    if (actual!=oracle if c['coverage']=='supported' else not actual.issubset(oracle)):mismatches.append({'cell':c['id'],'formula':c['formula'],'only_map':sorted(actual-oracle),'only_calc':sorted(oracle-actual)})
                    if len(examples)<3 and (any(model['cells'].get(a,{}).get('sheet')!=c['sheet'] for a in actual) or path.name!='Valuation.xlsx'):
                        examples.append({'cell':c['id'],'formula':c['formula'],'direct_precedents':sorted(oracle),'query_precedents':sorted(inspected)})
                doc.close(True)
                assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(data).digest()
                result={'workbook':path.name,'sha256':model['source']['sha256'],'supported_formulas':sum(c['coverage']=='supported' for c in model['cells'].values()),'partial_formulas':sum(c['coverage']=='partial' for c in model['cells'].values()),'unique_edges':edge_count,'mismatches':mismatches,'query_mismatches':query_mismatches,'representative_traces':examples,'precedents':manifest}
                results.append(result)
                print(path.name,len(manifest),'supported/partial formulas;',edge_count,'unique edges;',len(mismatches),'mismatches',flush=True)
            version=subprocess.check_output([os.environ.get('SOFFICE','libreoffice'),'--version'],text=True,env=dict(os.environ)).strip()
            output={'oracle':version,'method':'Calc XFormulaTokens.getTokens() reference structures independently expanded for every supported and partial formula; supported requires equality and partial requires every extracted edge to exist in Calc references. XFormulaQuery.queryPrecedents(False) additionally compared; cross-sheet query mismatches retained (LibreOffice bug 159973). No engine parser used to derive expected references.','results':results}
            (ROOT/'results/libreoffice.json').write_text(json.dumps(output,indent=2)+'\n')
            assert all(not r['mismatches'] for r in results),'Independent edge mismatches; see results/libreoffice.json'
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
