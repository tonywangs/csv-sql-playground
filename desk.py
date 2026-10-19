"""Exact typed selection and byte-preserving JSONL workbench; stdlib only."""
import argparse
import hashlib
import io
import json
import re
import secrets
import threading
import zipfile
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 8 * 1024 * 1024
MAX_LINES = 20000
MAX_LINE = 256 * 1024
MISSING = object()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate object key: ' + key[:80])
        result[key] = value
    return result


def number(text):
    if len(text) > 1000:
        raise ValueError('Number exceeds 1000 characters')
    value = Decimal(text)
    if not value.is_finite() or abs(value.adjusted()) > 10000:
        raise ValueError('Number is non-finite or exponent exceeds 10000')
    return value


def parse(text):
    value = json.loads(text, parse_int=number, parse_float=number,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-JSON constant')),
                       object_pairs_hook=pairs)
    # Surrogate escapes cannot represent Unicode scalar values. Bound nesting.
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 64:
            raise ValueError('Nesting exceeds 64 levels')
        if isinstance(item, str):
            item.encode('utf-8', errors='strict')
        elif isinstance(item, dict):
            stack.extend((x, depth + 1) for pair in item.items() for x in pair)
        elif isinstance(item, list):
            stack.extend((x, depth + 1) for x in item)
    return value


def kind(value):
    if value is MISSING: return 'missing'
    if value is None: return 'null'
    if isinstance(value, bool): return 'boolean'
    if isinstance(value, Decimal): return 'number'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    return 'object'


def path_parts(path):
    if not isinstance(path, str) or len(path) > 2048:
        raise ValueError('Path must be a string of at most 2048 characters')
    if path == '': return []
    if not path.startswith('/') or re.search(r'~(?![01])', path):
        raise ValueError('Use a JSON Pointer: /properties/mag or /geometry/coordinates/2')
    return [x.replace('~1', '/').replace('~0', '~') for x in path[1:].split('/')]


def lookup(value, parts):
    for part in parts:
        if isinstance(value, dict): value = value.get(part, MISSING)
        elif isinstance(value, list) and re.fullmatch(r'0|[1-9][0-9]*', part):
            value = value[int(part)] if len(part) < 9 and int(part) < len(value) else MISSING
        else: return MISSING
    return value


def compile_filters(filters):
    if not isinstance(filters, list) or len(filters) > 30:
        raise ValueError('Expected at most 30 filters')
    compiled = []
    for f in filters:
        if not isinstance(f, dict) or set(f) != {'path', 'op', 'value'}:
            raise ValueError('Filter requires path, op and value')
        parts = path_parts(f['path'])
        op = f['op']
        if op not in ('eq', 'gt', 'gte', 'lt', 'lte', 'type'):
            raise ValueError('Unknown filter operation')
        if not isinstance(f['value'], str) or len(f['value']) > 4096:
            raise ValueError('Filter value must be text, at most 4096 characters')
        if op == 'type':
            target = f['value']
            if target not in ('missing', 'null', 'boolean', 'number', 'string', 'array', 'object'):
                raise ValueError('Unknown type')
        else:
            target = parse(f['value'])
            if kind(target) not in ('null', 'boolean', 'number', 'string'):
                raise ValueError('Equality supports scalar values only')
            if op != 'eq' and kind(target) != 'number':
                raise ValueError('Ordered comparisons require a JSON number')
        compiled.append((parts, op, target))
    return compiled


def matches(value, compiled):
    for parts, op, target in compiled:
        actual = lookup(value, parts)
        if op == 'type': ok = kind(actual) == target
        elif kind(actual) != kind(target): ok = False
        elif op == 'eq': ok = actual == target
        elif op == 'gt': ok = actual > target
        elif op == 'gte': ok = actual >= target
        elif op == 'lt': ok = actual < target
        else: ok = actual <= target
        if not ok: return False
    return True


class Source:
    def __init__(self, raw):
        if len(raw) > MAX_BYTES: raise ValueError('File exceeds 8 MiB; processing incomplete')
        self.raw = raw
        self.hash = sha(raw)
        self.lines = []
        # Split only LF, never Unicode separators or lone CR.
        start = 0
        for end, byte in enumerate(raw):
            if byte == 10:
                self.lines.append(raw[start:end + 1]); start = end + 1
        if start < len(raw): self.lines.append(raw[start:])
        if len(self.lines) > MAX_LINES: raise ValueError('File exceeds 20000 lines; processing incomplete')
        self.values, self.errors = {}, {}
        for n, line in enumerate(self.lines, 1):
            try:
                if len(line) > MAX_LINE: raise ValueError('Line exceeds 256 KiB')
                self.values[n] = parse(line.decode('utf-8', errors='strict'))
            except (ValueError, RecursionError, InvalidOperation) as exc:
                self.errors[n] = str(exc)[:250]

    def select(self, filters, excluded):
        compiled = compile_filters(filters)
        if not isinstance(excluded, list) or len(excluded) > MAX_LINES or any(type(n) is not int or n not in self.values for n in excluded):
            raise ValueError('Excluded lines must be valid source line numbers')
        excluded = set(excluded)
        chosen = [n for n, v in self.values.items() if n not in excluded and matches(v, compiled)]
        counts = {'total': len(self.lines), 'included': len(chosen),
                  'excluded': len(self.values) - len(chosen), 'errors': len(self.errors)}
        return chosen, counts

    def export(self, filters, excluded):
        chosen, counts = self.select(filters, excluded)
        output = b''.join(self.lines[n - 1] for n in chosen)
        manifest = {'schema': 1, 'source_sha256': self.hash, 'source_bytes': len(self.raw),
                    'source_lines': chosen, 'filters': filters, 'excluded_lines': excluded,
                    'counts': counts, 'errors': [{'line': n, 'error': e} for n, e in self.errors.items()],
                    'complete': True, 'output_sha256': sha(output), 'output_bytes': len(output),
                    'newline_policy': 'Copy each original line including its original terminator; never add a final newline.'}
        return output, manifest


def create_server(port=8765):
    token = secrets.token_hex(24)
    lock = threading.Lock()
    state = {'source': None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def send(self, data, mime='application/json', code=200):
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(data)
        def result(self, value, code=200):
            self.send(json.dumps(value, ensure_ascii=True).encode(), code=code)
        def allowed(self):
            host = self.headers.get('Host', '')
            return host in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.allowed(): return self.result({'error': 'Invalid Host'}, 403)
            paths = {'/': ('static/index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('static/app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('static/style.css', 'text/css; charset=utf-8'),
                     '/demo.jsonl': ('data/earthquakes.jsonl', 'application/octet-stream')}
            if self.path == '/api/token': return self.result({'token': token})
            if self.path not in paths: return self.result({'error': 'Not found'}, 404)
            file, mime = paths[self.path]
            self.send((ROOT / file).read_bytes(), mime)
        def do_POST(self):
            if not self.allowed() or self.headers.get('X-Desk-Token') != token:
                return self.result({'error': 'Local session token required'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if size < 0 or size > MAX_BYTES: raise ValueError('Request exceeds 8 MiB or has no size; processing incomplete')
                raw = self.rfile.read(size)
                if len(raw) != size: raise ValueError('Incomplete request')
                if self.path == '/api/import':
                    source = Source(raw)
                    with lock: state['source'] = source
                    return self.result({'source_sha256': source.hash, 'source_bytes': len(raw), 'complete': True})
                data = json.loads(raw)
                with lock: source = state['source']
                if source is None or data.get('source_sha256') != source.hash:
                    raise ValueError('Source hash mismatch or source unavailable. Reattach the matching file.')
                filters, excluded = data.get('filters', []), data.get('excluded_lines', [])
                if self.path == '/api/query':
                    chosen, counts = source.select(filters, excluded)
                    offset = data.get('offset', 0)
                    if type(offset) is not int or offset < 0: raise ValueError('Invalid offset')
                    view = data.get('view', 'all')
                    if view not in ('all', 'included', 'errors'): raise ValueError('Unknown view')
                    numbers = chosen if view == 'included' else list(source.errors) if view == 'errors' else list(range(1, len(source.lines) + 1))
                    chosen_set = set(chosen)
                    rows = [{'line': n, 'status': 'error' if n in source.errors else 'included' if n in chosen_set else 'excluded',
                             'error': source.errors.get(n), 'text': source.lines[n - 1].decode('utf-8', errors='replace'),
                             'type': kind(source.values[n]) if n in source.values else 'error'} for n in numbers[offset:offset + 40]]
                    return self.result({'counts': counts, 'rows': rows, 'complete': True, 'view_total': len(numbers)})
                if self.path == '/api/export':
                    output, manifest = source.export(filters, excluded)
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                        archive.writestr('subset.jsonl', output)
                        archive.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
                    return self.send(buffer.getvalue(), 'application/zip')
                raise ValueError('Unknown endpoint')
            except (ValueError, TypeError, KeyError, RecursionError, InvalidOperation) as exc:
                self.result({'error': str(exc), 'complete': False}, 400)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f'JSONL Selection Desk: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
