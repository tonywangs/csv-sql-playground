"""Independent offline audit. Does not import the workbench implementation."""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

ABSENT = object()


def load_record(line):
    def unique(pairs):
        keys = [p[0] for p in pairs]
        if len(set(keys)) != len(keys): raise ValueError('duplicate key')
        return dict(pairs)
    def numeric(token):
        n = Decimal(token)
        if len(token) > 1000 or not n.is_finite() or abs(n.adjusted()) > 10000: raise ValueError('number limit')
        return n
    if len(line) > 262144: raise ValueError('line limit')
    obj = json.loads(line.decode('utf-8'), object_pairs_hook=unique, parse_int=numeric, parse_float=numeric,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
    def check(x, depth=0):
        if depth > 64: raise ValueError('depth limit')
        if isinstance(x, str): x.encode('utf-8')
        if isinstance(x, dict):
            for k, v in x.items(): check(k, depth+1); check(v, depth+1)
        if isinstance(x, list):
            for v in x: check(v, depth+1)
    check(obj)
    return obj


def typename(x):
    return 'missing' if x is ABSENT else {type(None): 'null', bool: 'boolean', Decimal: 'number', str: 'string', list: 'array', dict: 'object'}[type(x)]


def selected(record, filters):
    for rule in filters:
        value = record
        if rule['path']:
            for encoded in rule['path'][1:].split('/'):
                part = encoded.replace('~1', '/').replace('~0', '~')
                if type(value) is dict: value = value.get(part, ABSENT)
                elif type(value) is list and re.fullmatch('0|[1-9][0-9]*', part) and len(part)<9 and int(part)<len(value): value=value[int(part)]
                else: value=ABSENT
        if rule['op'] == 'type':
            if typename(value) != rule['value']: return False
        else:
            target = json.loads(rule['value'], parse_int=Decimal, parse_float=Decimal)
            if type(value) != type(target): return False
            op=rule['op']
            if op=='eq' and value != target: return False
            if op=='gt' and not value > target: return False
            if op=='gte' and not value >= target: return False
            if op=='lt' and not value < target: return False
            if op=='lte' and not value <= target: return False
    return True


def verify(source_path, subset_path, manifest_path):
    source, subset = Path(source_path).read_bytes(), Path(subset_path).read_bytes()
    m=json.loads(Path(manifest_path).read_text())
    assert m['schema']==1 and m['complete'] is True
    assert type(m['filters']) is list and len(m['filters']) <= 30, 'Invalid filters'
    for rule in m['filters']:
        assert type(rule) is dict and set(rule) == {'path', 'op', 'value'}, 'Invalid filter shape'
        pointer, op, text = rule['path'], rule['op'], rule['value']
        assert type(pointer) is str and len(pointer) <= 2048, 'Invalid path'
        assert (not pointer or pointer.startswith('/')) and not re.search(r'~(?![01])', pointer), 'Invalid JSON Pointer'
        assert op in ('eq', 'gt', 'gte', 'lt', 'lte', 'type'), 'Invalid operator'
        assert type(text) is str and len(text) <= 4096, 'Invalid filter value'
        if op == 'type':
            assert text in ('missing', 'null', 'string', 'number', 'boolean', 'array', 'object'), 'Invalid type'
        else:
            target = load_record(text.encode('utf-8'))
            assert typename(target) in ('null', 'string', 'number', 'boolean'), 'Invalid scalar'
            assert op == 'eq' or type(target) is Decimal, 'Ordering requires number'
    assert type(m['excluded_lines']) is list and len(m['excluded_lines']) <= 20000, 'Invalid exclusions'
    assert len(source)<=8388608
    assert hashlib.sha256(source).hexdigest()==m['source_sha256'], 'Source hash mismatch'
    assert hashlib.sha256(subset).hexdigest()==m['output_sha256'], 'Output hash mismatch'
    assert len(source)==m['source_bytes'] and len(subset)==m['output_bytes']
    # Deliberately use a regex iterator rather than Source's byte-offset scanner.
    lines=re.findall(rb'[^\n]*\n|[^\n]+\Z',source)
    assert len(lines)<=20000
    expected=[]; errors=[]; valid=[]
    for i, raw in enumerate(lines,1):
        try: record=load_record(raw)
        except (ValueError, RecursionError, InvalidOperation): errors.append(i);continue
        valid.append(i)
        if i not in m['excluded_lines'] and selected(record,m['filters']): expected.append(i)
    assert all(type(i) is int and i in valid for i in m['excluded_lines'])
    assert expected==m['source_lines'], 'Filter results or source order differ'
    assert b''.join(lines[i-1] for i in expected)==subset, 'Original record bytes differ'
    assert errors==[e['line'] for e in m['errors']], 'Error accounting differs'
    assert m['counts']=={'total':len(lines),'included':len(expected),'excluded':len(valid)-len(expected),'errors':len(errors)}
    print(f'Independent audit PASS: {len(lines)} total = {len(expected)} included + {len(valid)-len(expected)} excluded + {len(errors)} errors; every exported byte verified')
    return m['counts']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source');p.add_argument('subset');p.add_argument('manifest')
    a=p.parse_args();verify(a.source,a.subset,a.manifest)
