"""Bounded, non-evaluating OOXML dependency inspection."""
import hashlib
import io
import posixpath
import re
import zipfile
from collections import Counter
from defusedxml.ElementTree import fromstring
from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.utils.cell import column_index_from_string, get_column_letter

LIMITS = dict(upload_bytes=10*1024*1024, expanded_bytes=32*1024*1024,
              archive_entries=1000, cells=50000, range_cells=10000, edges=200000,
              trace_nodes=10000, formula_chars=8192)
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
RID = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
A1 = re.compile(r'\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})$')
REF = re.compile(r"(?:(?:'((?:[^']|'')+)'|([^'!]+))!)?(\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6})(?::(\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}))?$")
# A deliberately finite list: unfamiliar functions can change reference semantics.
FUNCTIONS = set('SUM AVERAGE MIN MAX COUNT COUNTA COUNTBLANK IF IFS IFERROR IFNA AND OR NOT TRUE FALSE ABS ROUND ROUNDUP ROUNDDOWN INT MOD POWER SQRT EXP LN LOG LOG10 SIGN SUMIF SUMIFS COUNTIF COUNTIFS AVERAGEIF AVERAGEIFS SUMPRODUCT SUBTOTAL AGGREGATE PMT PPMT IPMT PV FV NPV IRR XNPV XIRR RATE NPER VLOOKUP HLOOKUP MATCH INDEX CHOOSE ROW COLUMN ROWS COLUMNS DATE YEAR MONTH DAY DAYS TODAY NOW EOMONTH CONCATENATE CONCAT TEXT LEFT RIGHT MID LEN TRIM UPPER LOWER VALUE ISERROR ISNA ISNUMBER ISTEXT'.split())

def key(sheet, address):
    return "'" + sheet.replace("'", "''") + "'!" + address

def coords(a):
    m=A1.fullmatch(a)
    if not m: raise ValueError('Invalid A1 address')
    col=column_index_from_string(m[1].upper()); row=int(m[2])
    if col>16384 or row>1048576: raise ValueError('Address outside XLSX bounds')
    return col,row

def dependencies(formula, sheet, sheets):
    refs=[]; issues=[]
    if len(formula)>LIMITS['formula_chars']: return [],['Formula character limit']
    try: tokens=Tokenizer(formula).items
    except Exception: return [],['Unrecognized formula syntax (including spill references)']
    for i,t in enumerate(tokens):
        if t.type=='FUNC' and t.subtype=='OPEN':
            name=t.value[:-1].upper()
            if name not in FUNCTIONS: issues.append('Unresolved function: '+name)
        if t.type=='OP_IN' and t.value==':': issues.append('Computed range boundary')
        if t.type=='WHITE-SPACE' and i and i+1<len(tokens) and tokens[i-1].subtype=='RANGE' and tokens[i+1].subtype=='RANGE': issues.append('Intersection reference')
        if t.type=='OPERAND' and t.subtype=='ERROR': issues.append('Formula error literal: '+t.value)
        if t.type!='OPERAND' or t.subtype!='RANGE': continue
        m=REF.fullmatch(t.value)
        if not m:
            issues.append('Unresolved reference (name, table, spill, or non-A1): '+t.value); continue
        target=(m[1].replace("''", "'") if m[1] is not None else m[2]) or sheet
        if '[' in target or ']' in target or ':' in target:
            issues.append('External or 3D reference: '+t.value); continue
        # Excel sheet matching is case-insensitive.
        target=next((s for s in sheets if s.casefold()==target.casefold()),None)
        if target is None: issues.append('Missing sheet: '+t.value); continue
        try: c1,r1=coords(m[3]); c2,r2=coords(m[4] or m[3])
        except ValueError: issues.append('Out-of-bounds reference: '+t.value); continue
        c1,c2=sorted((c1,c2)); r1,r2=sorted((r1,r2))
        if (c2-c1+1)*(r2-r1+1)>LIMITS['range_cells']:
            issues.append('Range expansion limit: '+t.value); continue
        if len(refs)+(c2-c1+1)*(r2-r1+1)>LIMITS['edges']:
            issues.append('Formula edge limit: '+t.value); continue
        for row in range(r1,r2+1):
            for col in range(c1,c2+1): refs.append((key(target,get_column_letter(col)+str(row)),t.value))
    return list(dict.fromkeys(refs)),list(dict.fromkeys(issues))

def inspect(data, filename='workbook.xlsx'):
    if len(data)>LIMITS['upload_bytes']: raise ValueError('Workbook exceeds 10 MiB upload limit')
    if not data.startswith(b'PK'): raise ValueError('Expected unencrypted XLSX ZIP; encrypted/legacy workbooks are unsupported')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist()
        if len(entries)>LIMITS['archive_entries'] or sum(x.file_size for x in entries)>LIMITS['expanded_bytes']: raise ValueError('Archive expansion limit exceeded')
        if len({x.filename for x in entries})!=len(entries): raise ValueError('Duplicate archive members')
        if any(x.flag_bits & 1 for x in entries): raise ValueError('Encrypted archive unsupported')
        def xml(p):
            raw=z.read(p)
            if len(raw)>LIMITS['expanded_bytes']: raise ValueError('XML size limit')
            return fromstring(raw)
        wb=xml('xl/workbook.xml')
        if wb.tag!=NS+'workbook': raise ValueError('Only transitional SpreadsheetML XLSX supported')
        rels={r.get('Id'):r for r in xml('xl/_rels/workbook.xml.rels')}
        sheets=[]; paths=[]
        for s in wb.findall(NS+'sheets/'+NS+'sheet'):
            name=s.get('name'); rel=rels[s.get(RID)]
            if rel.get('TargetMode')=='External' or not rel.get('Type','').endswith('/worksheet'): raise ValueError('External/non-worksheet sheets unsupported')
            target=rel.get('Target',''); path=posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/'+target)
            if not path.startswith('xl/'): raise ValueError('Invalid worksheet path')
            if not name or name.casefold() in [n.casefold() for n in sheets]: raise ValueError('Duplicate or empty sheet name')
            sheets.append(name); paths.append(path)
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(si.itertext()) for si in xml('xl/sharedStrings.xml')]
        cells={}; masters={}; pending=[]
        for sheet,path in zip(sheets,paths):
            for c in xml(path).iter(NS+'c'):
                if len(cells)>=LIMITS['cells']: raise ValueError('Cell count exceeds 50,000')
                addr=c.get('r','');coords(addr); addr=addr.replace('$','').upper(); k=key(sheet,addr)
                if k in cells: raise ValueError('Duplicate cell address')
                f=c.find(NS+'f'); v=c.findtext(NS+'v'); typ=c.get('t','n')
                value=v
                if typ=='s' and v is not None: value=strings[int(v)]
                if typ=='inlineStr': value=''.join(c.find(NS+'is').itertext()) if c.find(NS+'is') is not None else ''
                node=dict(id=k,sheet=sheet,address=addr,kind='formula' if f is not None else 'literal',value=value if f is None else None,cached=v if f is not None else None,data_type=typ,formula=None,source_formula=None,formula_attributes={},issues=[],coverage='literal')
                if f is not None:
                    node['formula_attributes']=dict(f.attrib);node['source_formula']=f.text or '';node['formula']='='+(f.text or '')
                    ft=f.get('t','normal')
                    if ft=='shared':
                        si=f.get('si')
                        if f.text: masters[(sheet,si)]=(addr,node['formula'])
                        else: pending.append((node,si))
                    elif ft!='normal': node['issues'].append('Unsupported formula type: '+ft)
                cells[k]=node
        for node,si in pending:
            try:
                origin,formula=masters[(node['sheet'],si)]
                node['formula']=Translator(formula,origin=origin).translate_formula(node['address'])
            except Exception: node['issues'].append('Unresolved shared formula master/translation')
        edges=[]
        for node in cells.values():
            if node['kind']!='formula': continue
            refs,issues=dependencies(node['formula'],node['sheet'],sheets)
            node['issues']+=issues
            if node['formula']=='=': node['issues'].append('Empty formula')
            if len(edges)+len(refs)>LIMITS['edges']:
                node['issues'].append('Workbook edge limit'); refs=[]
            edges.extend(dict(source=node['id'],target=target,reference=ref,formula=node['formula']) for target,ref in refs)
            node['coverage']='partial' if node['issues'] and refs else 'unsupported' if node['issues'] else 'supported'
        counts=dict(Counter(n['coverage'] for n in cells.values()))
        return dict(version=1,source=dict(name=filename,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)),sheets=sheets,cells=cells,edges=edges,coverage=counts,limits=LIMITS,defined_names=[dict(n.attrib,text=n.text) for n in wb.findall(NS+'definedNames/'+NS+'definedName')],warnings=['Potential static dependencies only; branch execution and calculation correctness are not verified.','Cached results have unknown freshness. No recalculation, macro execution, or external fetching.'])
