#!/usr/bin/env python3
"""Local-only stateless analysis server. Run: python3 server.py"""
import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
from pivot import analyze, bundle, unpack_project, MAX_BYTES

ROOT = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, raw, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        authority = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') not in (authority, f'localhost:{self.server.server_port}'):
            return False
        return self.headers.get('Origin') in (None, f'http://{authority}', f'http://localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.allowed():
            return self.respond(403, b'Local origin required', 'text/plain')
        routes = {'/': ('web/index.html', 'text/html; charset=utf-8'), '/app.js': ('web/app.js', 'text/javascript'),
                  '/style.css': ('web/style.css', 'text/css'), '/demo.csv': ('data/penguins.csv', 'text/csv'),
                  '/demo-source.json': ('data/source.json', 'application/json')}
        route = routes.get(urlparse(self.path).path)
        if not route:
            return self.respond(404, b'Not found', 'text/plain')
        self.respond(200, (ROOT / route[0]).read_bytes(), route[1])

    def do_POST(self):
        if not self.allowed():
            return self.respond(403, b'Local origin required', 'text/plain')
        try:
            if self.path not in ('/api/analyze', '/api/export'):
                raise ValueError('Unknown operation.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BYTES * 2:
                raise ValueError('Request exceeds 4 MiB.')
            payload = json.loads(self.rfile.read(length))
            raw = base64.b64decode(payload['data'], validate=True)
            config, sha = payload.get('config'), payload.get('expected_hash')
            if payload.get('project') is not None:
                config, sha = unpack_project(payload['project'])
            result = analyze(raw, payload.get('name', 'source.csv'), config, sha)
            if self.path == '/api/export':
                self.respond(200, bundle(result), 'application/zip')
            else:
                self.respond(200, json.dumps(result, ensure_ascii=False).encode(), 'application/json')
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
            self.respond(400, json.dumps({'error': str(exc)}).encode(), 'application/json')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f'CSV Pivot Desk: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
