#!/usr/bin/env python3
"""Launch with python3 app.py; binds only IPv4 loopback."""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import secrets
import tempfile
from desk import MAX_DB, Unsupported, compare, snapshot

ROOT=Path(__file__).resolve().parent
TOKEN=secrets.token_urlsafe(32)

def document():
    return (ROOT/'static/index.html').read_text().replace('/* STYLE */',(ROOT/'static/style.css').read_text()).replace('/* SCRIPT */',(ROOT/'static/app.js').read_text()).replace('__TOKEN__',TOKEN)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self, status, data, content_type='application/json'):
        body=data.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type+'; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers(); self.wfile.write(body)
    def allowed_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.allowed_host():
            return self.reply(403,'{"error":"Invalid host"}')
        if self.path=='/': return self.reply(200,document(),'text/html')
        self.reply(404,'{"error":"Not found"}')
    def do_POST(self):
        if not self.allowed_host() or self.headers.get('X-Desk-Token')!=TOKEN:
            return self.reply(403,'{"error":"Invalid local request token"}')
        origin=self.headers.get('Origin')
        if origin and origin != 'http://'+self.headers['Host']:
            return self.reply(403,'{"error":"Cross-origin request rejected"}')
        if self.path!='/api/compare': return self.reply(404,'{"error":"Not found"}')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>23*1024*1024: raise Unsupported('Request exceeds upload limit')
            self.connection.settimeout(30)
            data=json.loads(self.rfile.read(length))
            identities=data.get('identities',{})
            if not isinstance(identities,dict) or any(not isinstance(v,list) or any(not isinstance(k,str) for k in v) for v in identities.values()):
                raise Unsupported('Invalid identity selection')
            with tempfile.TemporaryDirectory(prefix='snapshot-desk-') as directory:
                snapshots=[]
                for side in ('before','after'):
                    if data.get('demo') is True:
                        path=ROOT/'demo'/f'{side}.sqlite'; label=f'OurAirports {side}'
                    else:
                        upload=data[side]
                        raw=base64.b64decode(upload['data'],validate=True)
                        if len(raw)>MAX_DB: raise Unsupported('Upload exceeds 8 MiB')
                        path=Path(directory)/f'{side}.sqlite'; path.write_bytes(raw)
                        label=str(upload['name'])[:200]
                    snap=snapshot(path,label)
                    provenance=json.loads((ROOT/'demo/provenance.json').read_text())
                    for source in provenance['snapshots'].values():
                        if snap['sha256']==source['sqlite_sha256']:
                            snap['provenance']={'dataset':provenance['dataset'],'license':provenance['license'],**source}
                    snapshots.append(snap)
                result=compare(*snapshots,identities)
            self.reply(200,json.dumps(result,ensure_ascii=True))
        except (ValueError,KeyError,TypeError,OSError) as exc:
            self.reply(400,json.dumps({'error':str(exc),'status':'incomplete'}))

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=HTTPServer(('127.0.0.1',args.port),Handler)
    print(f'SQLite Snapshot Desk: http://127.0.0.1:{server.server_port} (Ctrl-C to stop)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=='__main__': main()
