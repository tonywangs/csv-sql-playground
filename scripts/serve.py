"""Loopback-only static server; no uploads, telemetry, or external runtime assets."""
import http.server, pathlib, argparse
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument('--port',type=int,default=8000); a=p.parse_args()
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if any(part.startswith('.') or part=='node_modules' for part in self.path.split('/')):
            self.send_error(404); return
        super().do_GET()
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()
print(f'Chart Point Desk: http://127.0.0.1:{a.port}',flush=True)
http.server.ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
