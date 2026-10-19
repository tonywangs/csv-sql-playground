"""Loopback-only application; no workbook bytes are written to disk."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote
import json
import argparse
from engine import inspect, LIMITS
ROOT=Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def allowed(self):
        host=self.headers.get('Host','')
        return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}') and self.headers.get('Origin', 'http://'+host)=='http://'+host
    def send(self,code,body,typ='application/json'):
        self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.allowed(): return self.send(403,b'{}')
        path=urlparse(self.path).path
        files={'/':'static/index.html','/app.js':'static/app.js','/graph.js':'static/graph.js','/style.css':'static/style.css'}
        files.update({'/demo/'+n:'fixtures/'+n for n in ['Loan.xlsx','CashFlowCompany.xlsx','Valuation.xlsx']})
        if path not in files: return self.send(404,b'{}')
        p=ROOT/files[path];typ={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[p.suffix]
        self.send(200,p.read_bytes(),typ)
    def do_POST(self):
        if not self.allowed(): return self.send(403,b'{}')
        if self.path!='/api/inspect': return self.send(404,b'{}')
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>LIMITS['upload_bytes']: raise ValueError('Upload must be between 1 byte and 10 MiB')
            self.connection.settimeout(30)
            data=self.rfile.read(size)
            if len(data)!=size: raise ValueError('Truncated upload')
            name=unquote(self.headers.get('X-Filename','workbook.xlsx'))[:255]
            result=inspect(data,name)
            self.send(200,json.dumps(result,ensure_ascii=True).encode())
        except Exception as e:
            self.send(400,json.dumps({'error':str(e)[:500]}).encode())

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);args=ap.parse_args()
    print(f'Formula Map: http://127.0.0.1:{args.port}',flush=True)
    HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
