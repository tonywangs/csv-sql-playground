#!/usr/bin/env python3
"""Local-only, stateless CSV Join Desk. Launch: python3 app.py"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from join_engine import request
ROOT = Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, mime='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(data)
    def valid_origin(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host') == expected and self.headers.get('Origin', 'http://' + expected) == 'http://' + expected
    def do_GET(self):
        if not self.valid_origin(): return self.reply(403, b'{}')
        files = {'/': ('web/index.html', 'text/html; charset=utf-8'), '/app.js': ('web/app.js', 'text/javascript; charset=utf-8'), '/style.css': ('web/style.css', 'text/css'), '/demo/airports.csv': ('data/airports.csv', 'text/csv'), '/demo/countries.csv': ('data/countries.csv', 'text/csv')}
        item = files.get(urlparse(self.path).path)
        if not item: return self.reply(404, b'{}')
        self.reply(200, (ROOT / item[0]).read_bytes(), item[1])
    def do_POST(self):
        if self.path != '/api' or not self.valid_origin(): return self.reply(403, b'{}')
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 6 * 1024 * 1024: raise ValueError('Request exceeds 6 MiB or is empty.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict): raise ValueError('Request must be an object.')
            result = request(body)
            self.reply(200, json.dumps(result, ensure_ascii=False).encode())
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            self.reply(400, json.dumps({'error': str(exc)}).encode())
    def log_message(self, *args): pass
if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=8765); args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    server.timeout = 30
    print(f'CSV Join Desk: http://127.0.0.1:{args.port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
