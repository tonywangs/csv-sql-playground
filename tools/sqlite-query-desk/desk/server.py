"""Single-user loopback server. No third-party runtime dependencies."""
import argparse, base64, json, os, secrets, sqlite3, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from desk.core import MAX_DB, bundle, encode, parameters, settings, sha, validate_header
ROOT = Path(__file__).resolve().parents[1]

def run_worker(request, timeout):
    p = subprocess.run([sys.executable, '-m', 'desk.worker'], input=encode(request), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, cwd=ROOT)
    if p.returncode: raise ValueError('Worker stopped by resource limit or unsupported database')
    out = json.loads(p.stdout)
    if 'error' in out: raise ValueError(out['error'])
    return out['ok']

class State:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='sqlite-desk-')
        self.path = Path(self.directory.name)/'snapshot.sqlite'
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.source = None
        self.schema = []
        self.job = None
    def busy(self): return self.job and self.job['status'] == 'running'
    def connect(self, data, name, stable):
        if stable is not True: raise ValueError('Confirm a closed standalone snapshot with no WAL/journal companions')
        validate_header(data)
        if name.lower().endswith(('-wal', '-shm', '-journal')): raise ValueError('Companion files cannot be imported')
        with self.lock:
            if self.busy(): raise ValueError('Cancel or finish the current query before reconnecting')
            candidate = self.path.with_suffix('.candidate')
            candidate.write_bytes(data)
            try: schema = run_worker({'inspect':True, 'path':str(candidate)}, 3)
            except Exception:
                candidate.unlink(missing_ok=True)
                raise
            candidate.replace(self.path)
            self.source = {'name':str(name)[:200], 'sha256':sha(data), 'bytes':len(data)}
            self.schema = schema
            self.job = None
            return {'source':self.source, 'schema':schema}
    def start(self, req):
        with self.lock:
            if not self.source: raise ValueError('Connect a database first')
            if self.busy(): raise ValueError('One query at a time')
            if req.get('source_hash') != self.source['sha256']: raise ValueError('Source changed: explicitly reconnect and rerun')
            limits = settings(req.get('settings', {}))
            parameters(req.get('parameters', {}))
            if not isinstance(req.get('sql'), str) or not req['sql'].strip() or len(req['sql'].encode()) > 65536: raise ValueError('SQL required; maximum 64 KiB')
            job = {'id':secrets.token_hex(12), 'status':'running', 'cancel':threading.Event(), 'result':None}
            self.job = job
            request = {'path':str(self.path), 'sql':req['sql'], 'parameters':req.get('parameters', {}), 'settings':limits, 'source':dict(self.source)}
            threading.Thread(target=self.work, args=(job, request), daemon=True).start()
            return {'id':job['id']}
    def work(self, job, req):
        started = time.monotonic()
        p = None
        try:
            p = subprocess.Popen([sys.executable, '-m', 'desk.worker'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
            payload = encode(req)
            while True:
                if job['cancel'].is_set() or time.monotonic()-started > req['settings']['seconds'] + .25:
                    p.kill()
                    p.communicate()
                    result = {k:v for k,v in req.items() if k != 'path'}
                    result.update(format='sqlite-query-desk.result.v1', sqlite_version=sqlite3.sqlite_version, status='interrupted', reason='cancelled' if job['cancel'].is_set() else 'time limit', rows=[], columns=[], row_count=0, elapsed_ms=round((time.monotonic()-started)*1000,2), source_unchanged=sha(self.path.read_bytes())==req['source']['sha256'])
                    break
                try:
                    out, err = p.communicate(input=payload, timeout=.05)
                    if p.returncode: raise ValueError('Worker stopped by memory/CPU limit or invalid database')
                    value = json.loads(out)
                    if 'error' in value: raise ValueError(value['error'])
                    result = value['ok']
                    break
                except subprocess.TimeoutExpired: payload = None
        except Exception as exc:
            result = {k:v for k,v in req.items() if k != 'path'}
            result.update(format='sqlite-query-desk.result.v1', status='error', reason=str(exc), rows=[], columns=[], row_count=0, source_unchanged=sha(self.path.read_bytes())==req['source']['sha256'], sqlite_version=sqlite3.sqlite_version)
        finally:
            if p and p.poll() is None: p.kill(); p.communicate()
        with self.lock:
            job['result'] = result
            job['status'] = 'done'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, data, status=200, mime='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)
    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.valid_host(): return self.send(encode({'error':'Use the printed loopback URL'}), 403)
        route = urlparse(self.path).path
        state = self.server.state
        if route == '/api/session': return self.send(encode({'token':state.token}))
        if route.startswith('/api/job/'):
            if self.headers.get('X-Desk-Token') != state.token: return self.send(b'{}', 403)
            with state.lock:
                job = state.job
                if not job or route.rsplit('/',1)[-1] != job['id']: return self.send(encode({'error':'Job no longer available'}), 404)
                return self.send(encode({k:job[k] for k in ('id','status','result')}))
        static = {'/':('web/index.html','text/html; charset=utf-8'), '/app.js':('web/app.js','text/javascript; charset=utf-8'), '/style.css':('web/style.css','text/css; charset=utf-8'), '/demo/provenance.json':('demo/provenance.json','application/json')}
        if route not in static: return self.send(b'{}',404)
        path, mime = static[route]
        return self.send((ROOT/path).read_bytes(), mime=mime)
    def do_POST(self):
        state = self.server.state
        expected = f'http://127.0.0.1:{self.server.server_port}'
        if not self.valid_host() or self.headers.get('X-Desk-Token') != state.token or self.headers.get('Origin', expected) != expected:
            return self.send(encode({'error':'Invalid local request'}),403)
        try:
            if self.headers.get('Content-Type') != 'application/json': raise ValueError('JSON required')
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 12*1024*1024: raise ValueError('Request exceeds 12 MiB or is empty')
            self.connection.settimeout(10)
            req = json.loads(self.rfile.read(length))
            if not isinstance(req,dict): raise ValueError('Object required')
            if self.path == '/api/demo':
                out = state.connect((ROOT/'demo/ourairports.sqlite').read_bytes(), 'OurAirports countries + regions', True)
            elif self.path == '/api/import':
                out = state.connect(base64.b64decode(req['data'], validate=True), req['name'], req.get('stable'))
            elif self.path == '/api/run': out = state.start(req)
            elif self.path == '/api/cancel':
                with state.lock:
                    if not state.job or state.job['id'] != req.get('id'): raise ValueError('Unknown job')
                    state.job['cancel'].set()
                out = {'ok':True}
            elif self.path == '/api/export':
                with state.lock:
                    if not state.job or state.job['id'] != req.get('id') or state.busy(): raise ValueError('Run a query before export')
                    return self.send(bundle(state.job['result'], req.get('acknowledge') is True), mime='application/zip')
            else: return self.send(b'{}',404)
            self.send(encode(out))
        except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
            self.send(encode({'error':str(exc)}),400)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=4173)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.state = State()
    print(f'SQLite Query Desk: http://127.0.0.1:{server.server_port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if server.state.busy(): server.state.job['cancel'].set()
        server.server_close()
if __name__ == '__main__': main()
