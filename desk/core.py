"""Bounded read-only query worker and reproducible export encoding."""
import base64, csv, hashlib, io, json, math, re, sqlite3, time, zipfile
from pathlib import Path
MAX_DB = 8 * 1024 * 1024
DEFAULTS = {'rows': 1000, 'bytes': 1024 * 1024, 'seconds': 3}
MAXIMA = {'rows': 10000, 'bytes': 4 * 1024 * 1024, 'seconds': 10}

def encode(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')

def sha(data): return hashlib.sha256(data).hexdigest()

def settings(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS): raise ValueError('Invalid execution settings')
    out = DEFAULTS | raw
    for k, v in out.items():
        if type(v) is not int or not 1 <= v <= MAXIMA[k]: raise ValueError(f'{k} must be an integer from 1 to {MAXIMA[k]}')
    return out

def parameters(raw):
    if not isinstance(raw, dict) or len(raw) > 100: raise ValueError('Parameters must be an object with at most 100 names')
    out = {}
    for name, spec in raw.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) or not isinstance(spec, dict) or set(spec) != {'type', 'value'}:
            raise ValueError('Each parameter needs a simple name and exactly type/value')
        kind, value = spec['type'], spec['value']
        if kind == 'null':
            if value is not None: raise ValueError('null parameter value must be null')
            out[name] = None
        elif kind == 'integer':
            if not isinstance(value, str) or not re.fullmatch(r'-?(0|[1-9][0-9]*)', value): raise ValueError('Integers must be decimal strings')
            out[name] = int(value)
            if not -(2**63) <= out[name] < 2**63: raise ValueError('Integer outside signed 64-bit range')
        elif kind == 'real':
            if not isinstance(value, str): raise ValueError('Reals must be strings')
            out[name] = float(value)
            if not math.isfinite(out[name]): raise ValueError('Real must be finite')
        elif kind == 'text':
            if not isinstance(value, str): raise ValueError('Text must be a string')
            out[name] = value
        elif kind == 'blob':
            if not isinstance(value, str): raise ValueError('BLOB must be base64 string')
            out[name] = base64.b64decode(value, validate=True)
        else: raise ValueError('Unknown parameter type')
    return out

def cell(v):
    if v is None: return {'type':'null', 'value':None}
    if isinstance(v, bytes): return {'type':'blob', 'value':base64.b64encode(v).decode()}
    if isinstance(v, int): return {'type':'integer', 'value':str(v)}
    if isinstance(v, float): return {'type':'real', 'value':repr(v)}
    return {'type':'text', 'value':v}

def validate_header(data):
    if len(data) > MAX_DB: raise ValueError('Database exceeds 8 MiB')
    if len(data) < 100 or data[:16] != b'SQLite format 3\x00': raise ValueError('Not a SQLite 3 database')
    if data[18:20] != b'\x01\x01': raise ValueError('WAL or unsupported journal format: export a closed DELETE-mode snapshot first')

def connection(path):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
    con.enable_load_extension(False)
    con.execute('PRAGMA query_only=ON')
    con.execute('PRAGMA trusted_schema=OFF')
    con.execute('PRAGMA temp_store=MEMORY')
    con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4 * 1024 * 1024)
    con.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 65536)
    con.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 256)
    con.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
    con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100)
    con.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    return con

# Explicit allowlist: schema-mutating, transaction, pragma, attachment and extension
# actions are denied by default. Only built-in scalar/aggregate functions listed here.
FUNCTIONS = set('abs avg char coalesce concat count date datetime format glob hex ifnull iif instr julianday length like likelihood likely lower ltrim max min nullif printf quote replace round rtrim sign strftime substr substring sum time total trim typeof unicode unixepoch unlikely upper zeroblob row_number rank dense_rank lag lead first_value last_value nth_value percent_rank cume_dist ntile'.split())
def authorize(action, a, b, db, trigger):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE): return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (b or '').lower() in FUNCTIONS: return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY

def execute(path, request):
    start = time.monotonic()
    limits = settings(request.get('settings', {}))
    sql = request.get('sql')
    if not isinstance(sql, str) or not sql.strip() or len(sql.encode()) > 65536: raise ValueError('SQL required; maximum 64 KiB')
    params = parameters(request.get('parameters', {}))
    before = sha(Path(path).read_bytes())
    result = {'format':'sqlite-query-desk.result.v1', 'source':request['source'], 'sql':sql, 'parameters':request.get('parameters', {}), 'settings':limits, 'sqlite_version':sqlite3.sqlite_version, 'columns':[], 'rows':[], 'status':'error', 'reason':None}
    con = connection(path)
    con.set_authorizer(authorize)
    con.set_progress_handler(lambda: int(time.monotonic()-start >= limits['seconds']), 1000)
    try:
        cursor = con.execute(sql, params)
        if cursor.description is None: raise ValueError('A result-producing read query is required')
        result['columns'] = [d[0] for d in cursor.description]
        used = len(encode(result['columns'])) + 2
        if used > limits['bytes']:
            result['status'], result['reason'] = 'truncated', 'byte limit (column metadata)'
        else:
            result['status'] = 'complete'
            for row in cursor:
                if time.monotonic()-start >= limits['seconds']:
                    result['status'], result['reason'] = 'interrupted', 'time limit'
                    break
                typed = [cell(v) for v in row]
                size = len(encode(typed)) + (1 if result['rows'] else 0)
                if len(result['rows']) >= limits['rows'] or used + size > limits['bytes']:
                    result['status'], result['reason'] = 'truncated', 'row limit' if len(result['rows']) >= limits['rows'] else 'byte limit'
                    break
                result['rows'].append(typed)
                used += size
    except (sqlite3.Error, ValueError, UnicodeError) as exc:
        result['status'] = 'interrupted' if isinstance(exc, sqlite3.Error) and getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_INTERRUPT else 'error'
        result['reason'] = 'time limit' if result['status'] == 'interrupted' else str(exc)
        if result['status'] == 'error': result['rows'] = []
    finally: con.close()
    result['row_count'] = len(result['rows'])
    result['elapsed_ms'] = round((time.monotonic()-start)*1000, 2)
    result['source_unchanged'] = before == sha(Path(path).read_bytes()) == request['source']['sha256']
    if not result['source_unchanged']:
        result.update(status='error', reason='Snapshot hash changed; reconnect and rerun', rows=[], row_count=0)
    return result

def inspect(path):
    con = connection(path)
    until = time.monotonic() + 2
    con.set_progress_handler(lambda: int(time.monotonic()>until), 1000)
    try:
        tables = con.execute("SELECT name,sql FROM sqlite_schema WHERE type='table' ORDER BY name LIMIT 101").fetchall()
        if len(tables) > 100: raise ValueError('At most 100 tables supported')
        out = []
        for name, sql in tables:
            if sql and re.match(r'CREATE\s+VIRTUAL', sql, re.I): raise ValueError('Virtual tables are unsupported')
            columns = con.execute('PRAGMA table_info("'+name.replace('"','""')+'")').fetchall()
            out.append({'name':name, 'sql':sql, 'columns':[{'name':c[1], 'type':c[2], 'primary_key':bool(c[5])} for c in columns]})
        return out
    finally: con.close()

def bundle(result, acknowledge=False):
    if result['status'] == 'error' or not result['source_unchanged']: raise ValueError('Failed or invalidated results cannot be exported')
    if result['status'] != 'complete' and not acknowledge: raise ValueError('Explicit partial-result acknowledgment required')
    typed = encode(result) + b'\n'
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(result['columns'])
    writer.writerows([[c['value'] if c['value'] is not None else '' for c in row] for row in result['rows']])
    csv_bytes = stream.getvalue().encode('utf-8')
    manifest = {k:v for k,v in result.items() if k != 'rows'}
    manifest.update(format='sqlite-query-desk.manifest.v1', partial_acknowledged=acknowledge, csv_warning='Types lost; NULL and empty text both empty; BLOB is base64. Formula-like text is not neutralized: import as text, not spreadsheet formulas.', output_hashes={'results.csv':sha(csv_bytes), 'results.json':sha(typed)})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in [('results.csv',csv_bytes), ('results.json',typed), ('manifest.json',encode(manifest)+b'\n')]:
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()
