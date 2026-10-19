"""Bounded, typed SQLite snapshot comparison. Python standard library only."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

MAX_DB = 8 * 1024 * 1024
MAX_REPORT = 8 * 1024 * 1024
MAX_ROWS = 20000
MAX_CELL = 65536
MAX_COLUMNS = 128
MAX_TABLES = 100
MAX_MATERIALIZED = 8 * 1024 * 1024

class Unsupported(ValueError):
    pass

def quote(name):
    return '"' + name.replace('"', '""') + '"'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    if value is None:
        return ('null', None)
    if isinstance(value, bytes):
        if len(value) > MAX_CELL:
            raise Unsupported('BLOB exceeds 64 KiB cell limit')
        return ('blob', value.hex())
    if isinstance(value, str):
        if len(value.encode('utf-8')) > MAX_CELL:
            raise Unsupported('TEXT exceeds 64 KiB cell limit')
        return ('text', value)
    if isinstance(value, int):
        return ('integer', str(value))
    return ('real', value.hex())

def snapshot(path, label=None):
    """Read only a detached stable database. Never run queries supplied by users."""
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size > MAX_DB:
        raise Unsupported('Database missing or exceeds 8 MiB')
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(path) + suffix).exists():
            raise Unsupported('WAL/SHM/journal companion present; use SQLite backup to a detached snapshot')
    raw = path.read_bytes()
    if raw[:16] != b'SQLite format 3\x00':
        raise Unsupported('Not an ordinary SQLite database; encrypted databases are unsupported')
    if raw[18:20] != b'\x01\x01':
        raise Unsupported('WAL-mode database unsupported; create a detached backup in DELETE journal mode')
    sha = digest(raw)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        connection.enable_load_extension(False)
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        # Generated columns can expand a tiny database into huge values. Bound
        # SQLite's allocation as well as the values retained by this process.
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        deadline = time.monotonic() + 10
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise Unsupported('SQLite integrity check failed')
        objects = [dict(zip(('type', 'name', 'table', 'sql'), r)) for r in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name")]
        kinds = {r[1]: r[2] for r in connection.execute('PRAGMA table_list')}
        tables = {}
        row_budget = MAX_ROWS
        value_budget = MAX_MATERIALIZED
        for obj in objects:
            if obj['type'] != 'table' or obj['name'].startswith('sqlite_'):
                continue
            if len(tables) >= MAX_TABLES:
                raise Unsupported('More than 100 user tables')
            name = obj['name']
            table = {'sql': obj['sql'], 'columns': [], 'rows': [], 'error': None, 'count': None}
            tables[name] = table
            try:
                if kinds.get(name) != 'table':
                    raise Unsupported('Virtual/shadow table unsupported (not read)')
                if re.search(r'\bCOLLATE\b', obj['sql'] or '', re.I):
                    raise Unsupported('Explicit collations unsupported; equality uses storage classes and exact values')
                columns = connection.execute('PRAGMA table_xinfo(' + quote(name) + ')').fetchall()
                table['columns'] = [{'name': c[1], 'type': c[2], 'notnull': c[3], 'default': c[4], 'pk': c[5], 'hidden': c[6]} for c in columns]
                table['count'] = connection.execute('SELECT count(*) FROM ' + quote(name)).fetchone()[0]
                if len(columns) > MAX_COLUMNS:
                    raise Unsupported('More than 128 columns')
                if table['count'] > row_budget:
                    raise Unsupported('Snapshot exceeds 20,000 supported rows')
                # Use scan ordinal as a snapshot-local source reference, never as identity.
                rows = connection.execute('SELECT ' + ','.join(quote(c['name']) for c in table['columns']) + ' FROM ' + quote(name))
                for row in rows:
                    encoded = tuple(encode(v) for v in row)
                    value_budget -= sum(len(v[1].encode('utf-8')) if v[1] is not None else 4 for v in encoded)
                    if value_budget < 0:
                        raise Unsupported('Snapshot exceeds 8 MiB materialized value budget')
                    table['rows'].append(encoded)
                row_budget -= len(table['rows'])
            except (sqlite3.Error, Unsupported, UnicodeError) as exc:
                table['error'] = str(exc)
                table['rows'] = []
        if digest(path.read_bytes()) != sha or any(Path(str(path) + s).exists() for s in ('-wal', '-shm', '-journal')):
            raise Unsupported('Input changed during read; comparison discarded')
        return {'label': label or path.name, 'sha256': sha, 'bytes': len(raw), 'objects': objects, 'tables': tables}
    except sqlite3.Error as exc:
        raise Unsupported('Unsupported, corrupt, or interrupted SQLite input: ' + str(exc)) from exc
    finally:
        connection.close()

def compare_table(before, after, keys):
    result = {'status': 'complete', 'identity': keys, 'identity_valid': None,
              'warnings': [], 'records': [], 'counts': dict.fromkeys(('added','removed','changed','unchanged','ambiguous_before','ambiguous_after'), 0),
              'before_count': before['count'] if before else 0, 'after_count': after['count'] if after else 0,
              'before_schema': before['sql'] if before else None, 'after_schema': after['sql'] if after else None,
              'columns': (after or before)['columns']}
    bcols = [c['name'] for c in before['columns']] if before else None
    acols = [c['name'] for c in after['columns']] if after else None
    errors = [x['error'] for x in (before, after) if x and x['error']]
    if before and after and bcols != acols:
        errors.append('Incompatible column names/order; schema shown, records not compared')
    columns = acols or bcols or []
    if len(keys) != len(set(keys)) or any(k not in columns for k in keys):
        errors.append('Invalid identity columns')
    if errors:
        result.update(status='unsupported', warnings=errors)
        return result
    left = before['rows'] if before else []
    right = after['rows'] if after else []
    counts = result['counts']
    def emit(kind, bs, ats):
        result['records'].append({'kind': kind, 'before': [{'ordinal': i+1, 'values': row} for i,row in bs],
                                  'after': [{'ordinal': i+1, 'values': row} for i,row in ats]})
        if kind == 'ambiguous':
            counts['ambiguous_before'] += len(bs)
            counts['ambiguous_after'] += len(ats)
        else:
            counts[kind] += max(len(bs), len(ats))
    if keys:
        indices = [columns.index(k) for k in keys]
        groups = [defaultdict(list), defaultdict(list)]
        for rows, group in zip((left,right),groups):
            for i,row in enumerate(rows):
                group[tuple(row[j] for j in indices)].append((i,row))
        invalid = 0
        for key in sorted(groups[0].keys() | groups[1].keys(), key=repr):
            bs, ats = groups[0][key], groups[1][key]
            if any(v[0] == 'null' for v in key) or len(bs)>1 or len(ats)>1:
                invalid += 1
                emit('ambiguous', bs, ats)
            elif not bs:
                emit('added', [], ats)
            elif not ats:
                emit('removed', bs, [])
            else:
                emit('unchanged' if bs[0][1] == ats[0][1] else 'changed', bs, ats)
        result['identity_valid'] = not invalid
        if invalid:
            result['warnings'].append(f'{invalid} identity groups contain NULL or duplicates; no definite match claimed for those groups')
    else:
        result['warnings'].append('No identity: exact multiset comparison only. Residual rows on both sides have ambiguous correspondence.')
        groups = [defaultdict(list), defaultdict(list)]
        for rows, group in zip((left,right),groups):
            for i,row in enumerate(rows):
                group[row].append((i,row))
        lb, ra = [], []
        for row in sorted(groups[0].keys() | groups[1].keys(), key=repr):
            bs, ats = groups[0][row], groups[1][row]
            n = min(len(bs),len(ats))
            for j in range(n):
                emit('unchanged', [bs[j]], [ats[j]])
            lb.extend(bs[n:]); ra.extend(ats[n:])
        if lb and ra:
            emit('ambiguous', lb, ra)
        else:
            for r in lb: emit('removed', [r], [])
            for r in ra: emit('added', [], [r])
    assert len(left) == counts['removed'] + counts['changed'] + counts['unchanged'] + counts['ambiguous_before']
    assert len(right) == counts['added'] + counts['changed'] + counts['unchanged'] + counts['ambiguous_after']
    return result

def compare(before, after, identities=None):
    identities = identities or {}
    tables = {n: compare_table(before['tables'].get(n), after['tables'].get(n), identities.get(n, []))
              for n in sorted(before['tables'].keys() | after['tables'].keys())}
    result = {'format': 'sqlite-snapshot-desk/1', 'status': 'complete' if all(t['status']=='complete' for t in tables.values()) else 'incomplete',
              'semantics': 'Storage-class-sensitive equality; exact text/BLOB bytes, real float.hex; scan ordinals are references, never identities. Views, triggers and indexes are schema-only.',
              'before': {k:v for k,v in before.items() if k!='tables'}, 'after': {k:v for k,v in after.items() if k!='tables'}, 'tables': tables}
    if len(json.dumps(result, ensure_ascii=True).encode()) > MAX_REPORT:
        raise Unsupported('Report exceeds 8 MiB; comparison not returned. Use smaller snapshots.')
    return result
